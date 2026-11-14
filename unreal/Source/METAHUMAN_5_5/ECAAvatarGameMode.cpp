#include "ECAAvatarGameMode.h"
#include "ECAAvatarSession.h"
#include "EngineUtils.h"

AECAAvatarGameMode::AECAAvatarGameMode()
{
    DefaultPawnClass = nullptr;
    HUDClass = AECAAvatarHUD::StaticClass();
}

void AECAAvatarHUD::DrawHUD()
{
    Super::DrawHUD();
    for (TActorIterator<AECAAvatarSession> Session(GetWorld()); Session; ++Session)
    {
        DrawText(Session->Status, FLinearColor::White, 36.0f, 30.0f, nullptr, 1.3f);
        break;
    }
}
