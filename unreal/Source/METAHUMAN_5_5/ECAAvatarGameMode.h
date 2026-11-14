#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/HUD.h"
#include "ECAAvatarGameMode.generated.h"

UCLASS()
class METAHUMAN_5_5_API AECAAvatarHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
};

UCLASS()
class METAHUMAN_5_5_API AECAAvatarGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AECAAvatarGameMode();
};
