#include "MetaHumanBackend.h"

#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "HAL/PlatformFilemanager.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/ConfigCacheIni.h"
#include "Logging/LogMacros.h"
#include "Serialization/JsonSerializer.h"
#include "Dom/JsonObject.h"
#include "Components/AudioComponent.h"
#include "Sound/SoundWave.h"
#include "Sound/SoundWaveProcedural.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"

DEFINE_LOG_CATEGORY_STATIC(LogMetaHumanBackend, Log, All);

FString UMetaHumanBackend::LastDownloadedAudioPath;
FString UMetaHumanBackend::BackendBaseUrl;
TMap<UAudioComponent*, UMetaHumanBackend::FAnswerAudioPlaybackBinding> UMetaHumanBackend::ActivePlaybackBindings;

static const TCHAR* MetaHumanBackendConfigSection = TEXT("/Script/METAHUMAN_5_5.MetaHumanBackend");
static const TCHAR* MetaHumanBackendBaseUrlKey = TEXT("BackendBaseUrl");
static const TCHAR* MetaHumanBackendDefaultBaseUrl = TEXT("http://127.0.0.1:8000");

// Kleiner Helper: FString -> UTF8 Bytes
static void AppendUtf8(const FString& In, TArray<uint8>& Out)
{
    FTCHARToUTF8 Converter(*In);
    Out.Append(reinterpret_cast<const uint8*>(Converter.Get()), Converter.Length());
}

static uint16 ReadUInt16LE(const TArray<uint8>& Data, int32 Offset)
{
    return static_cast<uint16>(Data[Offset]) |
        (static_cast<uint16>(Data[Offset + 1]) << 8);
}

static uint32 ReadUInt32LE(const TArray<uint8>& Data, int32 Offset)
{
    return static_cast<uint32>(Data[Offset]) |
        (static_cast<uint32>(Data[Offset + 1]) << 8) |
        (static_cast<uint32>(Data[Offset + 2]) << 16) |
        (static_cast<uint32>(Data[Offset + 3]) << 24);
}

static void WriteInt16LE(TArray<uint8>& Data, int32 Offset, int16 Value)
{
    const uint16 Raw = static_cast<uint16>(Value);
    Data[Offset] = static_cast<uint8>(Raw & 0xff);
    Data[Offset + 1] = static_cast<uint8>((Raw >> 8) & 0xff);
}

static int16 ReadInt16LE(const TArray<uint8>& Data, int32 Offset)
{
    return static_cast<int16>(ReadUInt16LE(Data, Offset));
}

static void LimitPcm16InPlace(TArray<uint8>& Data, int32 Offset, int32 Size)
{
    if (Size < 2 || Offset < 0 || Offset + Size > Data.Num())
    {
        return;
    }

    constexpr int32 TargetPeak = 26869; // ~ -1.7 dBFS; reduce spikes without boosting quiet audio.
    int32 MaxAbsSample = 0;
    const int32 End = Offset + Size - 1;

    for (int32 Pos = Offset; Pos < End; Pos += 2)
    {
        const int32 Sample = static_cast<int32>(ReadInt16LE(Data, Pos));
        MaxAbsSample = FMath::Max(MaxAbsSample, FMath::Abs(Sample));
    }

    if (MaxAbsSample <= TargetPeak)
    {
        return;
    }

    const float Scale = static_cast<float>(TargetPeak) / static_cast<float>(MaxAbsSample);
    for (int32 Pos = Offset; Pos < End; Pos += 2)
    {
        const int32 Sample = static_cast<int32>(ReadInt16LE(Data, Pos));
        const int32 Scaled = FMath::Clamp(FMath::RoundToInt(static_cast<float>(Sample) * Scale), -32768, 32767);
        WriteInt16LE(Data, Pos, static_cast<int16>(Scaled));
    }

    UE_LOG(LogMetaHumanBackend, Log,
        TEXT("Limited PCM16 audio peak from %d to %d (scale %.3f)."),
        MaxAbsSample,
        TargetPeak,
        Scale);
}

static void LimitDecodedAudioInPlace(TArray<uint8>& Data)
{
    if (Data.Num() < 2)
    {
        return;
    }

    // WAV path: locate PCM16 fmt/data chunks and limit only sample bytes.
    if (Data.Num() >= 44 &&
        FMemory::Memcmp(Data.GetData(), "RIFF", 4) == 0 &&
        FMemory::Memcmp(Data.GetData() + 8, "WAVE", 4) == 0)
    {
        bool bIsPcm16 = false;
        int32 DataOffset = INDEX_NONE;
        int32 DataSize = 0;

        int32 Pos = 12;
        while (Pos + 8 <= Data.Num())
        {
            const uint32 ChunkSize = ReadUInt32LE(Data, Pos + 4);
            const int32 ChunkDataOffset = Pos + 8;
            if (ChunkDataOffset + static_cast<int64>(ChunkSize) > Data.Num())
            {
                break;
            }

            if (FMemory::Memcmp(Data.GetData() + Pos, "fmt ", 4) == 0 && ChunkSize >= 16)
            {
                const uint16 AudioFormat = ReadUInt16LE(Data, ChunkDataOffset);
                const uint16 BitsPerSample = ReadUInt16LE(Data, ChunkDataOffset + 14);
                bIsPcm16 = (AudioFormat == 1 && BitsPerSample == 16);
            }
            else if (FMemory::Memcmp(Data.GetData() + Pos, "data", 4) == 0)
            {
                DataOffset = ChunkDataOffset;
                DataSize = static_cast<int32>(ChunkSize);
            }

            Pos = ChunkDataOffset + static_cast<int32>(ChunkSize) + (ChunkSize & 1);
        }

        if (bIsPcm16 && DataOffset != INDEX_NONE)
        {
            LimitPcm16InPlace(Data, DataOffset, DataSize);
        }
        return;
    }

    // Raw PCM16 path used by CreateSoundWaveFromBytes.
    LimitPcm16InPlace(Data, 0, Data.Num());
}

TArray<uint8> UMetaHumanBackend::CustomDecodeBase64(const FString& SourceString)
{
    TArray<uint8> BinaryData;
    FBase64::Decode(SourceString, BinaryData);
    LimitDecodedAudioInPlace(BinaryData);
    return BinaryData;
}

USoundWaveProcedural* UMetaHumanBackend::CreateSoundWaveFromBytes(const TArray<uint8>& BinaryData, int32 SampleRate)
{
    if (BinaryData.Num() == 0)
    {
        return nullptr;
    }

    TArray<uint8> LimitedData = BinaryData;
    LimitDecodedAudioInPlace(LimitedData);

    USoundWaveProcedural* NewSoundWave = NewObject<USoundWaveProcedural>();
    NewSoundWave->SetSampleRate(SampleRate);
    NewSoundWave->NumChannels = 1;
    NewSoundWave->Duration = static_cast<float>(LimitedData.Num()) / (SampleRate * 2); // 16-bit = 2 bytes per sample.
    NewSoundWave->QueueAudio(LimitedData.GetData(), LimitedData.Num());

    return NewSoundWave;
}

void UMetaHumanBackend::SendAudioToBackend(const FString& InputFilePath)
{
    // 1) Pfad auflösen (relativ -> Saved/BouncedWavFiles)
    FString FullPath = InputFilePath;

    if (FPaths::IsRelative(FullPath))
    {
        // Unreal speichert Output von "Finish Recording Output" standardmäßig hier:
        // <Projekt>/Saved/BouncedWavFiles/<Dateiname>
        const FString BouncedDir =
            FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("BouncedWavFiles"));

        FullPath = FPaths::Combine(BouncedDir, FullPath);
    }

    UE_LOG(LogMetaHumanBackend, Log, TEXT("Resolved audio path: %s"), *FullPath);

    IPlatformFile& PlatformFile = FPlatformFileManager::Get().GetPlatformFile();

    if (!PlatformFile.FileExists(*FullPath))
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("Input file does not exist: %s"), *FullPath);
        return;
    }

    // 2) Datei laden
    TArray<uint8> FileData;
    if (!FFileHelper::LoadFileToArray(FileData, *FullPath))
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("Failed to load file: %s"), *FullPath);
        return;
    }

    // 3) POST /respond vorbereiten
    const FString BaseUrl = GetBackendBaseUrl();
    const FString Url = BuildBackendUrlFromBase(BaseUrl, TEXT("respond"));

    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request =
        FHttpModule::Get().CreateRequest();

    Request->SetURL(Url);
    Request->SetVerb(TEXT("POST"));

    const FString Boundary = TEXT("----UEBoundaryMetaHuman1234");
    const FString FileName = FPaths::GetCleanFilename(FullPath);

    FString HeaderPart = FString::Printf(
        TEXT("--%s\r\n")
        TEXT("Content-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n")
        TEXT("Content-Type: audio/wav\r\n\r\n"),
        *Boundary,
        *FileName
    );

    FString FooterPart = FString::Printf(
        TEXT("\r\n--%s--\r\n"),
        *Boundary
    );

    TArray<uint8> RequestContent;
    RequestContent.Reserve(HeaderPart.Len() + FileData.Num() + FooterPart.Len() + 32);

    AppendUtf8(HeaderPart, RequestContent);
    RequestContent.Append(FileData);
    AppendUtf8(FooterPart, RequestContent);

    Request->SetHeader(TEXT("Content-Type"),
        FString::Printf(TEXT("multipart/form-data; boundary=%s"), *Boundary));

    // 👇 Hier hängt dein Input-File zur späteren Löschung dran
    Request->SetHeader(TEXT("X-UE-InputFile"), FullPath);
    Request->SetHeader(TEXT("X-UE-BackendBaseUrl"), BaseUrl);

    Request->SetContent(RequestContent);

    Request->OnProcessRequestComplete().BindStatic(
        &UMetaHumanBackend::OnSendAudioResponse
    );

    if (!Request->ProcessRequest())
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("Failed to start HTTP request to %s"), *Url);
    }
    else
    {
        UE_LOG(LogMetaHumanBackend, Log, TEXT("Sending audio file '%s' to backend..."), *FullPath);
    }
}

void UMetaHumanBackend::OnSendAudioResponse(
    FHttpRequestPtr Request,
    FHttpResponsePtr Response,
    bool bWasSuccessful)
{
    if (!bWasSuccessful || !Response.IsValid())
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("Request to backend failed."));
        return;
    }

    const int32 Code = Response->GetResponseCode();
    const FString Body = Response->GetContentAsString();

    UE_LOG(LogMetaHumanBackend, Log,
        TEXT("Backend response: %d\n%s"),
        Code,
        *Body
    );

    if (Code != 200)
    {
        UE_LOG(LogMetaHumanBackend, Warning,
            TEXT("Non-200 response from backend. See log for body."));
        return;
    }

    // 1) Original-Inputfile aus Header holen und löschen
    const FString OriginalInputPath = Request->GetHeader(TEXT("X-UE-InputFile"));
    if (!OriginalInputPath.IsEmpty())
    {
        IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();
        if (PF.FileExists(*OriginalInputPath))
        {
            PF.DeleteFile(*OriginalInputPath);
            UE_LOG(LogMetaHumanBackend, Log, TEXT("Deleted original input file: %s"), *OriginalInputPath);
        }
    }

    // 2) JSON parsen und audio_file extrahieren
    TSharedPtr<FJsonObject> JsonObject;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Body);

    if (!FJsonSerializer::Deserialize(Reader, JsonObject) || !JsonObject.IsValid())
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("Failed to parse JSON from backend."));
        return;
    }

    FString AudioFileName;
    if (!JsonObject->TryGetStringField(TEXT("audio_file"), AudioFileName) || AudioFileName.IsEmpty())
    {
        UE_LOG(LogMetaHumanBackend, Warning, TEXT("No 'audio_file' field in backend response."));
        return;
    }

    UE_LOG(LogMetaHumanBackend, Log, TEXT("Backend created audio file: %s"), *AudioFileName);
    // Sanitize filename from backend (remove directories and backslashes)
    AudioFileName.ReplaceInline(TEXT("\\"), TEXT("/"));

    // 3) GET /audio/<filename>?delete=true
    const FString RequestBaseUrl = NormalizeBackendBaseUrl(Request->GetHeader(TEXT("X-UE-BackendBaseUrl")));
    const FString DownloadUrl = BuildBackendUrlFromBase(
        RequestBaseUrl.IsEmpty() ? GetBackendBaseUrl() : RequestBaseUrl,
        FString::Printf(TEXT("audio/%s?delete=true"), *AudioFileName)
    );

    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> DownloadRequest =
        FHttpModule::Get().CreateRequest();

    DownloadRequest->SetURL(DownloadUrl);
    DownloadRequest->SetVerb(TEXT("GET"));

    // Wir wollen den Dateinamen später noch kennen
    DownloadRequest->SetHeader(TEXT("X-UE-AudioFileName"), AudioFileName);

    DownloadRequest->OnProcessRequestComplete().BindStatic(
        &UMetaHumanBackend::OnDownloadAudioResponse
    );

    if (!DownloadRequest->ProcessRequest())
    {
        UE_LOG(LogMetaHumanBackend, Error,
            TEXT("Failed to start download request to %s"), *DownloadUrl);
    }
    else
    {
        UE_LOG(LogMetaHumanBackend, Log,
            TEXT("Downloading audio file from backend: %s"), *DownloadUrl);
    }
}

void UMetaHumanBackend::OnDownloadAudioResponse(
    FHttpRequestPtr Request,
    FHttpResponsePtr Response,
    bool bWasSuccessful)
{
    if (!bWasSuccessful || !Response.IsValid())
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("Audio download from backend failed."));
        return;
    }

    const int32 Code = Response->GetResponseCode();
    if (Code != 200)
    {
        UE_LOG(LogMetaHumanBackend, Error,
            TEXT("Audio download failed. HTTP %d"), Code);
        return;
    }

    // Bytes holen
    const TArray<uint8>& AudioData = Response->GetContent();

    // Zielpfad in deinem UE-Projekt, z.B. Saved/Audio/tts_1.wav
    FString FileName = Request->GetHeader(TEXT("X-UE-AudioFileName"));
    // Sanitize filename
    FileName.ReplaceInline(TEXT("\\"), TEXT("/"));
    if (FileName.IsEmpty())
    {
        FileName = TEXT("tts_download.wav");
    }

    const FString SaveDir = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Audio"));
    IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();
    PF.CreateDirectoryTree(*SaveDir);

    const FString LocalPath = FPaths::Combine(SaveDir, FileName);

    if (FFileHelper::SaveArrayToFile(AudioData, *LocalPath))
    {
        UE_LOG(LogMetaHumanBackend, Log,
            TEXT("Saved downloaded audio to: %s"), *LocalPath);

        // Store a project-relative reference (Saved/Audio/<filename>) so Blueprints can easily use it.
        LastDownloadedAudioPath = FString::Printf(TEXT("Saved/Audio/%s"), *FileName);
    }
    else
    {
        UE_LOG(LogMetaHumanBackend, Error,
            TEXT("Failed to save downloaded audio to: %s"), *LocalPath);
    }

}

void UMetaHumanBackend::PlayAnswerFromFile(
    const FString& FilePath,
    UAudioComponent* TargetAudioComponent,
    const FOnAnswerAudioPlaybackFinished& OnPlaybackFinished,
    bool bDeleteAfterPlayback)
{
    if (!TargetAudioComponent)
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("PlayAnswerFromFile: TargetAudioComponent is null."));
        return;
    }

    if (FilePath.IsEmpty())
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("PlayAnswerFromFile: File path is empty."));
        return;
    }

    FString ResolvedPath = FilePath;
    if (FPaths::IsRelative(ResolvedPath))
    {
        ResolvedPath = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(), ResolvedPath);

        if (!FPaths::FileExists(*ResolvedPath))
        {
            const FString SavedCandidate = FPaths::Combine(FPaths::ProjectSavedDir(), FilePath);
            if (FPaths::FileExists(*SavedCandidate))
            {
                ResolvedPath = SavedCandidate;
            }
        }
    }

    IPlatformFile& PlatformFile = FPlatformFileManager::Get().GetPlatformFile();
    if (!PlatformFile.FileExists(*ResolvedPath))
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("PlayAnswerFromFile: File does not exist: %s"), *ResolvedPath);
        return;
    }

    USoundWave* LoadedSound = LoadWavFile(ResolvedPath);
    if (!LoadedSound)
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("PlayAnswerFromFile: Failed to load WAV file: %s"), *ResolvedPath);
        return;
    }

    TargetAudioComponent->Stop();
    TargetAudioComponent->SetSound(LoadedSound);

    if (OnPlaybackFinished.IsBound())
    {
        RegisterAudioFinishedDelegate(TargetAudioComponent, OnPlaybackFinished);
    }
    else
    {
        RemoveAudioFinishedDelegate(TargetAudioComponent);
    }

    TargetAudioComponent->Play(0.f);

    UE_LOG(LogMetaHumanBackend, Log, TEXT("Playing WAV file on audio component: %s"), *ResolvedPath);

    if (bDeleteAfterPlayback)
    {
        if (PlatformFile.DeleteFile(*ResolvedPath))
        {
            UE_LOG(LogMetaHumanBackend, Log, TEXT("Deleted audio file after playback: %s"), *ResolvedPath);

            if (!LastDownloadedAudioPath.IsEmpty())
            {
                FString LastResolved = LastDownloadedAudioPath;
                if (FPaths::IsRelative(LastResolved))
                {
                    LastResolved = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(), LastResolved);
                }

                FString NormalizedLast = LastResolved;
                FString NormalizedCurrent = ResolvedPath;
                FPaths::NormalizeFilename(NormalizedLast);
                FPaths::NormalizeFilename(NormalizedCurrent);

                if (NormalizedLast == NormalizedCurrent)
                {
                    LastDownloadedAudioPath.Reset();
                }
            }
        }
        else
        {
            UE_LOG(LogMetaHumanBackend, Warning, TEXT("Failed to delete audio file after playback: %s"), *ResolvedPath);
        }
    }
}

USoundWave* UMetaHumanBackend::LoadWavFile(const FString& FilePath)
{
    if (FilePath.IsEmpty())
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("LoadWavFile: File path is empty."));
        return nullptr;
    }

    TArray<uint8> FileBytes;
    if (!FFileHelper::LoadFileToArray(FileBytes, *FilePath))
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("LoadWavFile: Failed to read file: %s"), *FilePath);
        return nullptr;
    }

    if (FileBytes.Num() < 44)
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("LoadWavFile: File too small to be a valid WAV: %s"), *FilePath);
        return nullptr;
    }

    const uint8* Data = FileBytes.GetData();
    const int32 TotalSize = FileBytes.Num();

    auto MatchesFourCC = [](const uint8* Ptr, const ANSICHAR* Tag) -> bool
    {
        return Ptr[0] == Tag[0] &&
               Ptr[1] == Tag[1] &&
               Ptr[2] == Tag[2] &&
               Ptr[3] == Tag[3];
    };

    auto ReadUint16 = [](const uint8* Ptr) -> uint16
    {
        return static_cast<uint16>(Ptr[0] | (Ptr[1] << 8));
    };

    auto ReadUint32 = [](const uint8* Ptr) -> uint32
    {
        return static_cast<uint32>(
            Ptr[0] |
            (Ptr[1] << 8) |
            (Ptr[2] << 16) |
            (Ptr[3] << 24)
        );
    };

    if (!MatchesFourCC(Data, "RIFF") || !MatchesFourCC(Data + 8, "WAVE"))
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("LoadWavFile: Missing RIFF/WAVE headers in %s"), *FilePath);
        return nullptr;
    }

    int32 Offset = 12;
    bool bFoundFormat = false;
    bool bFoundData = false;

    uint16 AudioFormat = 0;
    uint16 NumChannels = 0;
    uint32 SampleRate = 0;
    uint16 BitsPerSample = 0;
    uint32 DataSize = 0;
    const uint8* PCMData = nullptr;

    while (Offset + 8 <= TotalSize)
    {
        const uint8* ChunkId = Data + Offset;
        const uint32 ChunkSize = ReadUint32(Data + Offset + 4);
        const int32 ChunkDataStart = Offset + 8;
        const int32 ChunkDataEnd = ChunkDataStart + static_cast<int32>(ChunkSize);

        if (ChunkDataEnd > TotalSize)
        {
            UE_LOG(LogMetaHumanBackend, Error, TEXT("LoadWavFile: Corrupt chunk in %s"), *FilePath);
            return nullptr;
        }

        if (MatchesFourCC(ChunkId, "fmt "))
        {
            if (ChunkSize < 16)
            {
                UE_LOG(LogMetaHumanBackend, Error, TEXT("LoadWavFile: Incomplete fmt chunk in %s"), *FilePath);
                return nullptr;
            }

            AudioFormat = ReadUint16(Data + ChunkDataStart);
            NumChannels = ReadUint16(Data + ChunkDataStart + 2);
            SampleRate = ReadUint32(Data + ChunkDataStart + 4);
            BitsPerSample = ReadUint16(Data + ChunkDataStart + 14);

            bFoundFormat = true;
        }
        else if (MatchesFourCC(ChunkId, "data"))
        {
            DataSize = ChunkSize;
            PCMData = Data + ChunkDataStart;
            bFoundData = true;
        }

        Offset = ChunkDataEnd;
        if (ChunkSize % 2 == 1)
        {
            ++Offset;
        }
    }

    if (!bFoundFormat || !bFoundData)
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("LoadWavFile: Missing fmt or data chunk in %s"), *FilePath);
        return nullptr;
    }

    if (AudioFormat != 1)
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("LoadWavFile: WAV is not PCM (format %d) in %s"), static_cast<int32>(AudioFormat), *FilePath);
        return nullptr;
    }

    if (BitsPerSample != 16)
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("LoadWavFile: Unsupported bit depth (%d) in %s"), static_cast<int32>(BitsPerSample), *FilePath);
        return nullptr;
    }

    if (SampleRate == 0 || NumChannels == 0 || DataSize == 0 || PCMData == nullptr)
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("LoadWavFile: Invalid audio metadata in %s"), *FilePath);
        return nullptr;
    }

    const uint32 BytesPerSample = BitsPerSample / 8;
    const uint32 FrameSize = NumChannels * BytesPerSample;
    const uint32 BytesPerSecond = SampleRate * FrameSize;

    if (BytesPerSample == 0 || FrameSize == 0 || BytesPerSecond == 0)
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("LoadWavFile: Computed invalid frame sizes for %s"), *FilePath);
        return nullptr;
    }

    USoundWaveProcedural* SoundWave = NewObject<USoundWaveProcedural>(GetTransientPackage());
    if (!SoundWave)
    {
        UE_LOG(LogMetaHumanBackend, Error, TEXT("LoadWavFile: Failed to allocate procedural sound wave for %s"), *FilePath);
        return nullptr;
    }

    const float DurationSeconds = static_cast<float>(DataSize) / static_cast<float>(BytesPerSecond);

    SoundWave->SoundGroup = SOUNDGROUP_Voice;
    SoundWave->NumChannels = NumChannels;
    SoundWave->SetSampleRate(SampleRate);
    SoundWave->Duration = DurationSeconds;
    SoundWave->bLooping = false;
    SoundWave->bProcedural = true;
    SoundWave->bStreaming = false;

    // QueueAudio makes an internal copy, so it's safe to release PCMData afterwards.
    SoundWave->QueueAudio(PCMData, DataSize);

    return SoundWave;
}

FString UMetaHumanBackend::GetLastDownloadedAudioPath()
{
    if (LastDownloadedAudioPath.IsEmpty())
    {
        return FString();
    }

    const FString FileName = FPaths::GetCleanFilename(LastDownloadedAudioPath);
    if (FileName.IsEmpty())
    {
        return FString();
    }

    return FString::Printf(TEXT("Saved/Audio/%s"), *FileName);
}

FString UMetaHumanBackend::GetBackendBaseUrl()
{
    LoadBackendBaseUrlFromConfigIfNeeded();
    return BackendBaseUrl;
}

FString UMetaHumanBackend::GetBackendWebSocketUrl()
{
    FString Url = GetBackendBaseUrl();
    if (Url.RemoveFromStart(TEXT("https://"), ESearchCase::IgnoreCase))
    {
        Url = TEXT("wss://") + Url;
    }
    else if (Url.RemoveFromStart(TEXT("http://"), ESearchCase::IgnoreCase))
    {
        Url = TEXT("ws://") + Url;
    }
    if (!Url.EndsWith(TEXT("/ws")))
    {
        Url += TEXT("/ws");
    }
    return Url;
}

void UMetaHumanBackend::SetBackendBaseUrl(const FString& NewBaseUrl, bool bSaveToConfig)
{
    const FString NormalizedUrl = NormalizeBackendBaseUrl(NewBaseUrl);
    if (NormalizedUrl.IsEmpty())
    {
        UE_LOG(LogMetaHumanBackend, Warning, TEXT("SetBackendBaseUrl: URL is empty. Keeping current value: %s"), *GetBackendBaseUrl());
        return;
    }

    BackendBaseUrl = NormalizedUrl;
    UE_LOG(LogMetaHumanBackend, Log, TEXT("Backend base URL set to: %s"), *BackendBaseUrl);

    if (bSaveToConfig)
    {
        SaveBackendBaseUrl();
    }
}

void UMetaHumanBackend::SaveBackendBaseUrl()
{
    LoadBackendBaseUrlFromConfigIfNeeded();

    if (GConfig)
    {
        FString ConfigValue = BackendBaseUrl;
        ConfigValue.RemoveFromStart(TEXT("http://"), ESearchCase::IgnoreCase);

        GConfig->SetString(MetaHumanBackendConfigSection, MetaHumanBackendBaseUrlKey, *ConfigValue, GEngineIni);
        GConfig->Flush(false, GEngineIni);
        UE_LOG(LogMetaHumanBackend, Log, TEXT("Saved backend base URL to config: %s"), *BackendBaseUrl);
    }
}

FString UMetaHumanBackend::NormalizeBackendBaseUrl(const FString& InBaseUrl)
{
    FString Normalized = InBaseUrl;
    Normalized.TrimStartAndEndInline();
    if (Normalized.Len() >= 2 && Normalized.StartsWith(TEXT("\"")) && Normalized.EndsWith(TEXT("\"")))
    {
        Normalized = Normalized.Mid(1, Normalized.Len() - 2);
        Normalized.TrimStartAndEndInline();
    }

    if (Normalized.Equals(TEXT("http:"), ESearchCase::IgnoreCase) ||
        Normalized.Equals(TEXT("https:"), ESearchCase::IgnoreCase))
    {
        UE_LOG(LogMetaHumanBackend, Warning,
            TEXT("BackendBaseUrl was read as '%s'. In .ini files, write it without http://, e.g. 127.0.0.1:8000."),
            *Normalized);
        return FString();
    }

    if (Normalized.StartsWith(TEXT("http:/"), ESearchCase::IgnoreCase) &&
        !Normalized.StartsWith(TEXT("http://"), ESearchCase::IgnoreCase))
    {
        Normalized.RemoveFromStart(TEXT("http:/"), ESearchCase::IgnoreCase);
        Normalized = FString::Printf(TEXT("http://%s"), *Normalized);
    }
    else if (Normalized.StartsWith(TEXT("https:/"), ESearchCase::IgnoreCase) &&
        !Normalized.StartsWith(TEXT("https://"), ESearchCase::IgnoreCase))
    {
        Normalized.RemoveFromStart(TEXT("https:/"), ESearchCase::IgnoreCase);
        Normalized = FString::Printf(TEXT("https://%s"), *Normalized);
    }

    if (!Normalized.IsEmpty() && !Normalized.Contains(TEXT("://")))
    {
        Normalized = FString::Printf(TEXT("http://%s"), *Normalized);
    }

    while (Normalized.EndsWith(TEXT("/")))
    {
        Normalized.LeftChopInline(1);
    }

    return Normalized;
}

FString UMetaHumanBackend::BuildBackendUrl(const FString& Path)
{
    return BuildBackendUrlFromBase(GetBackendBaseUrl(), Path);
}

FString UMetaHumanBackend::BuildBackendUrlFromBase(const FString& BaseUrl, const FString& Path)
{
    FString CleanPath = Path;
    CleanPath.TrimStartAndEndInline();

    while (CleanPath.StartsWith(TEXT("/")))
    {
        CleanPath.RightChopInline(1);
    }

    return FString::Printf(TEXT("%s/%s"), *NormalizeBackendBaseUrl(BaseUrl), *CleanPath);
}

void UMetaHumanBackend::LoadBackendBaseUrlFromConfigIfNeeded()
{
    if (!BackendBaseUrl.IsEmpty())
    {
        return;
    }

    FString ConfigUrl;
    if (GConfig)
    {
        GConfig->GetString(MetaHumanBackendConfigSection, MetaHumanBackendBaseUrlKey, ConfigUrl, GEngineIni);
    }

    BackendBaseUrl = NormalizeBackendBaseUrl(ConfigUrl);
    if (BackendBaseUrl.IsEmpty())
    {
        BackendBaseUrl = NormalizeBackendBaseUrl(MetaHumanBackendDefaultBaseUrl);
    }
}

void UMetaHumanBackend::ClearLastDownloadedAudioPath()
{
    LastDownloadedAudioPath.Reset();
}

bool UMetaHumanBackend::DeleteLocalFile(const FString& FilePath)
{
    if (FilePath.IsEmpty())
    {
        return false;
    }

    FString ResolvedPath = FilePath;
    IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();

    if (FPaths::IsRelative(ResolvedPath))
    {
        FString CandidatePath = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(), ResolvedPath);

        if (!PF.FileExists(*CandidatePath))
        {
            const FString SavedCandidate = FPaths::Combine(FPaths::ProjectSavedDir(), FilePath);
            if (PF.FileExists(*SavedCandidate))
            {
                CandidatePath = SavedCandidate;
            }
        }

        ResolvedPath = CandidatePath;
    }

    if (PF.FileExists(*ResolvedPath))
    {
        if (PF.DeleteFile(*ResolvedPath))
        {
            UE_LOG(LogMetaHumanBackend, Log, TEXT("Deleted local file: %s"), *ResolvedPath);

            if (!LastDownloadedAudioPath.IsEmpty())
            {
                FString LastResolved = LastDownloadedAudioPath;
                if (FPaths::IsRelative(LastResolved))
                {
                    LastResolved = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(), LastResolved);
                }

                FString NormalizedLast = LastResolved;
                FString NormalizedDeleted = ResolvedPath;
                FPaths::NormalizeFilename(NormalizedLast);
                FPaths::NormalizeFilename(NormalizedDeleted);

                if (NormalizedLast == NormalizedDeleted)
                {
                    LastDownloadedAudioPath.Reset();
                }
            }

            return true;
        }

        UE_LOG(LogMetaHumanBackend, Warning, TEXT("Failed to delete local file: %s"), *ResolvedPath);
    }
    else
    {
        UE_LOG(LogMetaHumanBackend, Warning, TEXT("DeleteLocalFile: File does not exist: %s"), *ResolvedPath);
    }

    return false;
}

void UMetaHumanBackend::CancelAnswerPlayback(UAudioComponent* AudioComponent)
{
    if (!AudioComponent)
    {
        return;
    }

    // Entfernt aktive Timer/Delegates und Eintrag aus ActivePlaybackBindings
    RemoveAudioFinishedDelegate(AudioComponent);

    // Stoppt die tatsächliche Audio-Wiedergabe
    AudioComponent->Stop();
}

void UMetaHumanBackend::RegisterAudioFinishedDelegate(
    UAudioComponent* AudioComponent,
    const FOnAnswerAudioPlaybackFinished& Delegate)
{
    if (!AudioComponent || !Delegate.IsBound())
        return;

    RemoveAudioFinishedDelegate(AudioComponent);

    FAnswerAudioPlaybackBinding Binding;
    Binding.Delegate = Delegate;
    Binding.NativeHandle = FDelegateHandle();
    ActivePlaybackBindings.Add(AudioComponent, Binding);

    float Duration = 0.f;
    if (USoundBase* Sound = AudioComponent->GetSound())
        Duration = Sound->GetDuration();
    if (Duration <= 0.f)
        Duration = 0.1f;

    if (UWorld* World = AudioComponent->GetWorld())
    {
        FTimerDelegate TimerDel;
        TimerDel.BindStatic(&UMetaHumanBackend::HandleAudioComponentPlaybackFinished, AudioComponent);

        FTimerHandle TimerHandle;
        World->GetTimerManager().SetTimer(TimerHandle, TimerDel, Duration, false);
    }
}

void UMetaHumanBackend::RemoveAudioFinishedDelegate(UAudioComponent* AudioComponent)
{
    if (!AudioComponent)
        return;

    ActivePlaybackBindings.Remove(AudioComponent);

    if (UWorld* World = AudioComponent->GetWorld())
        World->GetTimerManager().ClearAllTimersForObject(AudioComponent);
}

void UMetaHumanBackend::HandleAudioComponentPlaybackFinished(UAudioComponent* FinishedComponent)
{
    if (!FinishedComponent)
    {
        return;
    }

    if (FAnswerAudioPlaybackBinding* Binding = ActivePlaybackBindings.Find(FinishedComponent))
    {
        if (Binding->Delegate.IsBound())
        {
            Binding->Delegate.Execute(FinishedComponent);
        }

        if (Binding->NativeHandle.IsValid())
        {
            FinishedComponent->OnAudioFinishedNative.Remove(Binding->NativeHandle);
        }

        ActivePlaybackBindings.Remove(FinishedComponent);
    }
}

bool UMetaHumanBackend::LocalFileExists(const FString& FilePath)
{
    if (FilePath.IsEmpty())
    {
        return false;
    }

    FString ResolvedPath = FilePath;
    IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();

    if (FPaths::IsRelative(ResolvedPath))
    {
        // Erst versuchen wir das Projektverzeichnis (funktioniert für Pfade wie "Saved/Audio/xxx.wav"),
        // anschließend explizit das Saved-Verzeichnis.
        FString CandidatePath = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(), ResolvedPath);

        if (!PF.FileExists(*CandidatePath))
        {
            const FString SavedCandidate = FPaths::Combine(FPaths::ProjectSavedDir(), FilePath);
            if (PF.FileExists(*SavedCandidate))
            {
                CandidatePath = SavedCandidate;
            }
        }

        ResolvedPath = CandidatePath;
    }

    return PF.FileExists(*ResolvedPath);
}

void UMetaHumanBackend::DeleteAllRecordedAudio()
{
    const FString RecordedDir = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("BouncedWavFiles"));
    TArray<FString> Files;
    IFileManager::Get().FindFilesRecursive(Files, *RecordedDir, TEXT("*.*"), true, false);

    if (Files.IsEmpty())
    {
        UE_LOG(LogMetaHumanBackend, Log, TEXT("DeleteAllRecordedAudio: No files found in %s"), *RecordedDir);
        return;
    }

    IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();
    int32 NumDeleted = 0;

    for (const FString& File : Files)
    {
        if (PF.DeleteFile(*File))
        {
            ++NumDeleted;
        }
        else
        {
            UE_LOG(LogMetaHumanBackend, Warning, TEXT("DeleteAllRecordedAudio: Failed to delete %s"), *File);
        }
    }

    UE_LOG(LogMetaHumanBackend, Log, TEXT("DeleteAllRecordedAudio: Deleted %d file(s) from %s"), NumDeleted, *RecordedDir);
}

void UMetaHumanBackend::DeleteAllAnswerAudio()
{
    const FString AnswerDir = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Audio"));
    TArray<FString> Files;
    IFileManager::Get().FindFilesRecursive(Files, *AnswerDir, TEXT("*.*"), true, false);

    if (Files.IsEmpty())
    {
        UE_LOG(LogMetaHumanBackend, Log, TEXT("DeleteAllAnswerAudio: No files found in %s"), *AnswerDir);
        LastDownloadedAudioPath.Reset();
        return;
    }

    IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();
    int32 NumDeleted = 0;

    for (const FString& File : Files)
    {
        if (PF.DeleteFile(*File))
        {
            ++NumDeleted;
        }
        else
        {
            UE_LOG(LogMetaHumanBackend, Warning, TEXT("DeleteAllAnswerAudio: Failed to delete %s"), *File);
        }
    }

    LastDownloadedAudioPath.Reset();
    UE_LOG(LogMetaHumanBackend, Log, TEXT("DeleteAllAnswerAudio: Deleted %d file(s) from %s"), NumDeleted, *AnswerDir);
}
