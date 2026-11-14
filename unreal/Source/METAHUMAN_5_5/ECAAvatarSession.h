#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ECAAvatarSession.generated.h"

class UECAAvatarSettings;
class UCameraComponent;
class UACEAudioCurveSourceComponent;
class UAsyncActionAnimateCharacter;
class UCapturableSoundWave;
class IWebSocket;

// owns the selected character, microphone and conversation connection
UCLASS()
class METAHUMAN_5_5_API AECAAvatarSession : public AActor
{
    GENERATED_BODY()

public:
    AECAAvatarSession();
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;

    UFUNCTION(BlueprintCallable, Category="ECA")
    bool PrepareCharacter(bool bUseLocalProfile = true);

    UPROPERTY(EditAnywhere, AdvancedDisplay, Category="ECA", meta=(DisplayName="MetaHuman Blueprint Override"))
    TSoftClassPtr<AActor> MetaHumanBlueprint;

    UFUNCTION(BlueprintCallable, Category="ECA")
    void StartRecording();

    UFUNCTION(BlueprintCallable, Category="ECA")
    void FinishRecording();

    UFUNCTION(BlueprintCallable, Category="ECA")
    void SendAudioFile(const FString& FilePath);

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category="ECA")
    TObjectPtr<AActor> Character;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category="ECA")
    FString Status = TEXT("Connecting to backend...");

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category="ECA")
    FString LastResponse;

private:
    void Connect();
    void HandleMessage(const FString& Message);
    void SubmitAudio(const TArray<uint8>& Audio, uint64 Generation);
    void StopResponse();
    void PlayNextSentence();
    void RemoveCurrentAudio();
    void SetStatus(const FString& Text);
    FString IdleMessage() const;
    void ResponseFinished();

    UFUNCTION()
    void OnAnimationEnded();

    UFUNCTION()
    void OnAudioSent(bool bSuccess);

    UPROPERTY()
    TObjectPtr<UECAAvatarSettings> Settings;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UCameraComponent> Camera;

    UPROPERTY()
    TObjectPtr<UACEAudioCurveSourceComponent> CurveSource;

    UPROPERTY()
    TObjectPtr<UCapturableSoundWave> Capture;

    UPROPERTY()
    TObjectPtr<UAsyncActionAnimateCharacter> Animation;

    TSharedPtr<IWebSocket> Socket;
    TArray<TArray<uint8>> SentenceQueue;
    FString CurrentAudioPath;
    FString ActiveRequestId;
    FTimerHandle ReconnectTimer;
    FTimerHandle RecordingLimitTimer;
    uint64 RequestGeneration = 0;
    bool bRecording = false;
    bool bExporting = false;
    bool bPlaying = false;
    bool bResponseDone = false;
    bool bEnding = false;
};
