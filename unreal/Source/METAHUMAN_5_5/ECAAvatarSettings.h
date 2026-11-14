#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "InputCoreTypes.h"
#include "ECAAvatarSettings.generated.h"

class AActor;
class UAnimInstance;

// configuration for the reusable avatar scene
UCLASS(Config=ECA, DefaultConfig, meta=(DisplayName="Avatar"))
class METAHUMAN_5_5_API UECAAvatarSettings : public UDeveloperSettings
{
    GENERATED_BODY()

public:
    UECAAvatarSettings();
    virtual FName GetCategoryName() const override { return TEXT("ECA"); }

    UPROPERTY(Config, EditAnywhere, Category="Character", meta=(DisplayName="MetaHuman Blueprint"))
    TSoftClassPtr<AActor> MetaHumanClass;

    UPROPERTY(Config, EditAnywhere, Category="Connection")
    FString BackendUrl = TEXT("http://127.0.0.1:8000");

    UPROPERTY(Config, EditAnywhere, Category="Input")
    FKey PushToTalkKey;

    UPROPERTY(Config, EditAnywhere, Category="Animation")
    FName A2FProvider = TEXT("LocalA2F-Mark");

    UPROPERTY(Config, EditAnywhere, AdvancedDisplay, Category="Animation")
    FName FaceComponentName = TEXT("Face");

    UPROPERTY(Config, EditAnywhere, AdvancedDisplay, Category="Animation", meta=(DisplayName="ACE Face Anim Blueprint"))
    TSoftClassPtr<UAnimInstance> FaceAnimationClass;

    static UECAAvatarSettings* CreateEffectiveSettings(UObject* Outer, bool bUseLocalProfile = true);
    FString GetWebSocketUrl() const;
};
