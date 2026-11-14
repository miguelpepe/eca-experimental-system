#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Delegates/Delegate.h"
#include "Containers/Map.h"
#include "Misc/Base64.h"
#include "Misc/FileHelper.h"
#include "Sound/SoundWaveProcedural.h"
#include "MetaHumanBackend.generated.h"


class UAudioComponent;
class USoundWave;

DECLARE_DYNAMIC_DELEGATE_OneParam(FOnAnswerAudioPlaybackFinished, UAudioComponent*, AudioComponent);

UCLASS()
class METAHUMAN_5_5_API UMetaHumanBackend : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:

    // backend address from the project config
    UFUNCTION(BlueprintCallable, Category="MetaHuman Backend")
    static FString GetBackendBaseUrl();

    // websocket endpoint for the voice manager
    UFUNCTION(BlueprintPure, Category="MetaHuman Backend")
    static FString GetBackendWebSocketUrl();

    UFUNCTION(BlueprintCallable, Category = "Parser")
    static TArray<uint8> CustomDecodeBase64(const FString& SourceString);

UFUNCTION(BlueprintCallable, Category = "Parser")
static FString EncodeFileToBase64(const FString& FilePath)
{
    TArray<uint8> FileData;
    if (FFileHelper::LoadFileToArray(FileData, *FilePath))
    {
        return FBase64::Encode(FileData);
    }
    return FString("");
}

UFUNCTION(BlueprintCallable, Category = "Parser")
static FString EncodeBytesToBase64(const TArray<uint8>& Data)
{
    return FBase64::Encode(Data);
}

UFUNCTION(BlueprintCallable, Category = "AI_Audio")
static USoundWaveProcedural* CreateSoundWaveFromBytes(const TArray<uint8>& BinaryData, int32 SampleRate = 24000);

    // Setzt die Backend-Basis-URL zur Laufzeit. Optional direkt in der Config speichern.
    UFUNCTION(BlueprintCallable, Category="MetaHuman Backend")
    static void SetBackendBaseUrl(const FString& NewBaseUrl, bool bSaveToConfig = false);

    // Speichert die aktuell gesetzte Backend-Basis-URL in der Projekt-Config.
    UFUNCTION(BlueprintCallable, Category="MetaHuman Backend")
    static void SaveBackendBaseUrl();

    // Pfad der zuletzt heruntergeladenen Antwort-Audiodatei (Saved/Audio/...)
    UFUNCTION(BlueprintCallable, Category="MetaHuman Backend")
    static FString GetLastDownloadedAudioPath();

    // Setzt den gespeicherten Pfad zurück (z.B. nach dem Löschen).
    UFUNCTION(BlueprintCallable, Category="MetaHuman Backend")
    static void ClearLastDownloadedAudioPath();


    // Löscht eine lokale Datei, wenn sie existiert.
    UFUNCTION(BlueprintCallable, Category="MetaHuman Backend")
    static bool DeleteLocalFile(const FString& FilePath);

    // Löscht alle aufgezeichneten Audio-Dateien (Saved/BouncedWavFiles)
    UFUNCTION(BlueprintCallable, Category="MetaHuman Backend")
    static void DeleteAllRecordedAudio();

    // Löscht alle Antwort-Audio-Dateien (Saved/Audio) und vergisst den gespeicherten Pfad
    UFUNCTION(BlueprintCallable, Category="MetaHuman Backend")
    static void DeleteAllAnswerAudio();

    // Prüft, ob eine lokale Datei (z.B. Saved/Audio/...) existiert – relative Pfade werden wie in PlayAnswerFromFile aufgelöst.
    UFUNCTION(BlueprintCallable, Category="MetaHuman Backend")
    static bool LocalFileExists(const FString& FilePath);

    // Bricht die aktuelle Antwort-Wiedergabe ab und entfernt interne Timer/Delegates.
    UFUNCTION(BlueprintCallable, Category="MetaHuman Backend")
    static void CancelAnswerPlayback(UAudioComponent* AudioComponent);

public:

    /** Sends an audio file to the local FastAPI backend (/respond). */
    UFUNCTION(BlueprintCallable, Category="MetaHuman Backend")
    static void SendAudioToBackend(const FString& InputFilePath);

    /** Loads a WAV file from disk and plays it on the provided audio component. */
    UFUNCTION(BlueprintCallable, Category="MetaHuman Backend", meta=(AutoCreateRefTerm="OnPlaybackFinished"))
    static void PlayAnswerFromFile(
        const FString& FilePath,
        UAudioComponent* TargetAudioComponent,
        const FOnAnswerAudioPlaybackFinished& OnPlaybackFinished,
        bool bDeleteAfterPlayback = true);

private:

    // Callback for POST /respond
    static void OnSendAudioResponse(
        FHttpRequestPtr Request,
        FHttpResponsePtr Response,
        bool bWasSuccessful
    );

    // Callback for GET /audio/<filename>?delete=true
    static void OnDownloadAudioResponse(
        FHttpRequestPtr Request,
        FHttpResponsePtr Response,
        bool bWasSuccessful
    );

    // Loads a PCM WAV file into a transient USoundWave instance.
    static USoundWave* LoadWavFile(const FString& FilePath);

    static FString NormalizeBackendBaseUrl(const FString& InBaseUrl);
    static FString BuildBackendUrl(const FString& Path);
    static FString BuildBackendUrlFromBase(const FString& BaseUrl, const FString& Path);
    static void LoadBackendBaseUrlFromConfigIfNeeded();

    static void RegisterAudioFinishedDelegate(UAudioComponent* AudioComponent, const FOnAnswerAudioPlaybackFinished& Delegate);
    static void RemoveAudioFinishedDelegate(UAudioComponent* AudioComponent);
    static void HandleAudioComponentPlaybackFinished(UAudioComponent* FinishedComponent);

private:

    struct FAnswerAudioPlaybackBinding
    {
        FOnAnswerAudioPlaybackFinished Delegate;
        FDelegateHandle NativeHandle;
    };

    // interner Speicher für den zuletzt heruntergeladenen Audio-Pfad
    static FString LastDownloadedAudioPath;
    static FString BackendBaseUrl;

    static TMap<UAudioComponent*, FAnswerAudioPlaybackBinding> ActivePlaybackBindings;
};
