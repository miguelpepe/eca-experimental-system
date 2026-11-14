#include "ECAAvatarSession.h"

#include "ECAAvatarSettings.h"
#include "ACEAudioCurveSourceComponent.h"
#include "ACEBlueprintLibrary.h"
#include "AsyncActionAnimateCharacter.h"
#include "Async/Async.h"
#include "Camera/CameraComponent.h"
#include "Components/InputComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Dom/JsonObject.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "IWebSocket.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/Base64.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "RuntimeAudioExporter.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Sound/CapturableSoundWave.h"
#include "TimerManager.h"
#include "WebSocketsModule.h"

DEFINE_LOG_CATEGORY_STATIC(LogECA, Log, All);

AECAAvatarSession::AECAAvatarSession()
{
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
    Camera->SetupAttachment(RootComponent);
    Camera->SetRelativeLocation(FVector(430.0, 0.0, 100.0));
    Camera->SetRelativeRotation(FRotator(0.0, 180.0, 0.0));
    Camera->FieldOfView = 45.0f;
}

bool AECAAvatarSession::PrepareCharacter(bool bUseLocalProfile)
{
    if (IsValid(Character)) { return true; }
    Settings = UECAAvatarSettings::CreateEffectiveSettings(this, bUseLocalProfile);
    UClass* CharacterClass = MetaHumanBlueprint.IsNull()
        ? Settings->MetaHumanClass.LoadSynchronous() : MetaHumanBlueprint.LoadSynchronous();
    if (!CharacterClass)
    {
        SetStatus(TEXT("Select a MetaHuman Blueprint in Project Settings > ECA > Avatar."));
        return false;
    }
    FActorSpawnParameters Params;
    Params.Owner = this;
    Params.ObjectFlags |= RF_Transient;
    Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    Character = GetWorld()->SpawnActor<AActor>(CharacterClass, GetActorTransform(), Params);
    if (!Character) { SetStatus(TEXT("Could not create the selected MetaHuman.")); return false; }

    TArray<USkeletalMeshComponent*> Meshes;
    Character->GetComponents(Meshes);
    USkeletalMeshComponent* Face = nullptr;
    for (USkeletalMeshComponent* Mesh : Meshes)
    {
        if (Mesh->GetFName() == Settings->FaceComponentName) { Face = Mesh; break; }
    }
    UClass* FaceClass = Settings->FaceAnimationClass.LoadSynchronous();
    if (!Face || !FaceClass)
    {
        SetStatus(TEXT("MetaHuman Face component or ACE Face Anim Blueprint missing."));
        Character->Destroy();
        Character = nullptr;
        return false;
    }
    Face->SetAnimInstanceClass(FaceClass);
    Face->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    CurveSource = Character->FindComponentByClass<UACEAudioCurveSourceComponent>();
    if (!CurveSource)
    {
        CurveSource = NewObject<UACEAudioCurveSourceComponent>(Character, TEXT("ECAAudio"));
        Character->AddInstanceComponent(CurveSource);
        CurveSource->SetupAttachment(Face);
        CurveSource->RegisterComponent();
    }
    CurveSource->OnAnimationEnded.AddDynamic(this, &AECAAvatarSession::OnAnimationEnded);
    return true;
}

void AECAAvatarSession::BeginPlay()
{
    Super::BeginPlay();
    if (!PrepareCharacter(!FParse::Param(FCommandLine::Get(), TEXT("ECAPublicProfile")))) { return; }
    if (APlayerController* Player = UGameplayStatics::GetPlayerController(this, 0))
    {
        EnableInput(Player);
        InputComponent->BindKey(Settings->PushToTalkKey, IE_Pressed, this, &AECAAvatarSession::StartRecording);
        InputComponent->BindKey(Settings->PushToTalkKey, IE_Released, this, &AECAAvatarSession::FinishRecording);
        Player->SetViewTarget(this);
        Player->SetInputMode(FInputModeGameOnly());
        UE_LOG(LogECA, Display, TEXT("ECA_SESSION_READY: character=%s, input=%s"),
            *Character->GetClass()->GetPathName(), *Settings->PushToTalkKey.ToString());
    }
    Connect();
}

void AECAAvatarSession::Connect()
{
    if (bEnding || (Socket.IsValid() && Socket->IsConnected())) { return; }
    if (Socket.IsValid())
    {
        Socket->OnConnected().Clear();
        Socket->OnConnectionError().Clear();
        Socket->OnClosed().Clear();
        Socket->OnMessage().Clear();
        Socket->Close();
    }
    Socket = FWebSocketsModule::Get().CreateWebSocket(Settings->GetWebSocketUrl());
    Socket->OnConnected().AddWeakLambda(this, [this]()
    {
        SetStatus(IdleMessage());
        FString AudioFile;
        if (FParse::Value(FCommandLine::Get(), TEXT("ECAAudioFile="), AudioFile)) { SendAudioFile(AudioFile); }
    });
    const auto Retry = [this]()
    {
        if (bEnding) { return; }
        SetStatus(TEXT("Backend unavailable. Start the backend; reconnecting..."));
        GetWorldTimerManager().SetTimer(ReconnectTimer, this, &AECAAvatarSession::Connect, 3.0f, false);
    };
    Socket->OnConnectionError().AddWeakLambda(this, [Retry](const FString&) { Retry(); });
    Socket->OnClosed().AddWeakLambda(this, [Retry](int32, const FString&, bool) { Retry(); });
    Socket->OnMessage().AddUObject(this, &AECAAvatarSession::HandleMessage);
    Socket->Connect();
}

void AECAAvatarSession::StartRecording()
{
    if (bRecording || bExporting || !Character) { return; }
    if (!Socket.IsValid() || !Socket->IsConnected()) { SetStatus(TEXT("Start the backend first.")); return; }
    StopResponse();
    Capture = UCapturableSoundWave::CreateCapturableSoundWave();
    if (!Capture || !Capture->StartCapture(INDEX_NONE))
    {
        SetStatus(TEXT("Microphone unavailable. Check Windows microphone permissions."));
        Capture = nullptr;
        return;
    }
    bRecording = true;
    SetStatus(TEXT("Listening... Release the key to send."));
    GetWorldTimerManager().SetTimer(RecordingLimitTimer, this, &AECAAvatarSession::FinishRecording, 60.0f, false);
}

void AECAAvatarSession::FinishRecording()
{
    if (!bRecording || !Capture) { return; }
    GetWorldTimerManager().ClearTimer(RecordingLimitTimer);
    bRecording = false;
    bExporting = true;
    Capture->StopCapture();
    const uint64 Generation = RequestGeneration;
    const TWeakObjectPtr<AECAAvatarSession> WeakThis(this);
    URuntimeAudioExporter::ExportSoundWaveToBuffer(
        TWeakObjectPtr<UImportedSoundWave>(Capture), ERuntimeAudioFormat::Wav, 100,
        FRuntimeAudioExportOverrideOptions(),
        FOnAudioExportToBufferResultNative::CreateLambda([WeakThis, Generation](bool bSuccess, const TArray64<uint8>& Data)
        {
            TArray<uint8> Audio;
            if (bSuccess && Data.Num() <= MAX_int32) { Audio.Append(Data.GetData(), static_cast<int32>(Data.Num())); }
            AsyncTask(ENamedThreads::GameThread, [WeakThis, Generation, Audio = MoveTemp(Audio)]()
            {
                if (!WeakThis.IsValid() || WeakThis->bEnding) { return; }
                WeakThis->bExporting = false;
                WeakThis->Capture = nullptr;
                if (Audio.IsEmpty()) { WeakThis->SetStatus(TEXT("No audio recorded.")); return; }
                WeakThis->SubmitAudio(Audio, Generation);
            });
        }));
}

void AECAAvatarSession::SendAudioFile(const FString& FilePath)
{
    TArray<uint8> Audio;
    if (!FFileHelper::LoadFileToArray(Audio, *FilePath)) { SetStatus(TEXT("Audio file could not be read.")); return; }
    StopResponse();
    SubmitAudio(Audio, RequestGeneration);
}

void AECAAvatarSession::SubmitAudio(const TArray<uint8>& Audio, uint64 Generation)
{
    if (Generation != RequestGeneration || !Socket.IsValid() || !Socket->IsConnected()) { return; }
    TSharedRef<FJsonObject> Request = MakeShared<FJsonObject>();
    ActiveRequestId = FGuid::NewGuid().ToString();
    Request->SetStringField(TEXT("type"), TEXT("request"));
    Request->SetStringField(TEXT("request_id"), ActiveRequestId);
    Request->SetStringField(TEXT("audio_b64"), FBase64::Encode(Audio));
    FString Message;
    FJsonSerializer::Serialize(Request, TJsonWriterFactory<>::Create(&Message));
    bResponseDone = false;
    LastResponse.Reset();
    Socket->Send(Message);
    SetStatus(TEXT("Thinking..."));
}

void AECAAvatarSession::HandleMessage(const FString& Message)
{
    if (bEnding || bRecording || bExporting) { return; }
    TSharedPtr<FJsonObject> Event;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Message), Event) || !Event.IsValid())
    {
        SetStatus(TEXT("Invalid backend response."));
        return;
    }
    FString Type;
    Event->TryGetStringField(TEXT("type"), Type);
    FString RequestId;
    if (ActiveRequestId.IsEmpty() ||
        (Event->TryGetStringField(TEXT("request_id"), RequestId) && RequestId != ActiveRequestId)) { return; }
    if (Type == TEXT("sentence"))
    {
        FString Encoded;
        TArray<uint8> Audio;
        if (Event->TryGetStringField(TEXT("audio_b64"), Encoded) && FBase64::Decode(Encoded, Audio) && !Audio.IsEmpty())
        {
            SentenceQueue.Add(MoveTemp(Audio));
            PlayNextSentence();
        }
    }
    else if (Type == TEXT("done"))
    {
        Event->TryGetStringField(TEXT("response"), LastResponse);
        bResponseDone = true;
        if (!bPlaying && SentenceQueue.IsEmpty()) { ResponseFinished(); }
    }
    else if (Type == TEXT("stopped"))
    {
        StopResponse();
        SetStatus(IdleMessage());
    }
    else if (Type == TEXT("error"))
    {
        StopResponse();
        SetStatus(TEXT("The backend could not generate a response. Check its log."));
    }
}

void AECAAvatarSession::PlayNextSentence()
{
    if (bEnding || bPlaying || bRecording || SentenceQueue.IsEmpty()) { return; }
    const FString AudioDir = FPaths::ProjectSavedDir() / TEXT("ECAAudio");
    IFileManager::Get().MakeDirectory(*AudioDir, true);
    CurrentAudioPath = FPaths::ConvertRelativePathToFull(AudioDir / (FGuid::NewGuid().ToString() + TEXT(".wav")));
    if (!FFileHelper::SaveArrayToFile(SentenceQueue[0], *CurrentAudioPath))
    {
        SentenceQueue.Reset();
        SetStatus(TEXT("Could not save received audio."));
        return;
    }
    SentenceQueue.RemoveAt(0);
    bPlaying = true;
    SetStatus(TEXT("Speaking..."));
    Animation = UAsyncActionAnimateCharacter::AnimateCharacterFromWavFileAsync(
        this, Character, CurrentAudioPath, FAudio2FaceEmotion(), nullptr, Settings->A2FProvider);
    if (!Animation) { OnAudioSent(false); return; }
    Animation->AudioSendCompleted.AddDynamic(this, &AECAAvatarSession::OnAudioSent);
    Animation->Activate();
}

void AECAAvatarSession::OnAudioSent(bool bSuccess)
{
    if (bEnding || !bPlaying) { return; }
    if (!bSuccess)
    {
        bPlaying = false;
        SentenceQueue.Reset();
        RemoveCurrentAudio();
        SetStatus(TEXT("Face animation failed. Check the selected ACE provider and GPU."));
    }
}

void AECAAvatarSession::OnAnimationEnded()
{
    if (!bPlaying || bEnding) { return; }
    bPlaying = false;
    RemoveCurrentAudio();
    PlayNextSentence();
    if (!bPlaying)
    {
        if (bResponseDone) { ResponseFinished(); }
        else { SetStatus(TEXT("Thinking...")); }
    }
}

void AECAAvatarSession::StopResponse()
{
    ++RequestGeneration;
    ActiveRequestId.Reset();
    if (Socket.IsValid() && Socket->IsConnected()) { Socket->Send(TEXT("{\"type\":\"stop\"}")); }
    SentenceQueue.Reset();
    bPlaying = false;
    bResponseDone = true;
    if (Animation)
    {
        Animation->AudioSendCompleted.RemoveAll(this);
        Animation = nullptr;
    }
    if (Character) { UACEBlueprintLibrary::StopCharacter(Character); }
    RemoveCurrentAudio();
}

void AECAAvatarSession::RemoveCurrentAudio()
{
    if (!CurrentAudioPath.IsEmpty())
    {
        IFileManager::Get().Delete(*CurrentAudioPath);
        CurrentAudioPath.Reset();
    }
}

void AECAAvatarSession::SetStatus(const FString& Text)
{
    Status = Text;
    UE_LOG(LogECA, Log, TEXT("%s"), *Text);
}

FString AECAAvatarSession::IdleMessage() const
{
    return FString::Printf(TEXT("Hold %s to talk"), *Settings->PushToTalkKey.GetDisplayName().ToString());
}

void AECAAvatarSession::ResponseFinished()
{
    SetStatus(IdleMessage());
    UE_LOG(LogECA, Display, TEXT("ECA_RESPONSE_DONE: %s"), *LastResponse);
    if (FParse::Param(FCommandLine::Get(), TEXT("ECAExitWhenDone"))) { FPlatformMisc::RequestExit(false); }
}

void AECAAvatarSession::EndPlay(const EEndPlayReason::Type Reason)
{
    bEnding = true;
    GetWorldTimerManager().ClearTimer(ReconnectTimer);
    GetWorldTimerManager().ClearTimer(RecordingLimitTimer);
    if (Capture) { Capture->StopCapture(); }
    StopResponse();
    if (CurveSource) { CurveSource->OnAnimationEnded.RemoveAll(this); }
    if (Socket.IsValid())
    {
        Socket->OnConnected().Clear();
        Socket->OnConnectionError().Clear();
        Socket->OnClosed().Clear();
        Socket->OnMessage().Clear();
        Socket->Close();
        Socket.Reset();
    }
    if (Character) { Character->Destroy(); }
    Super::EndPlay(Reason);
}
