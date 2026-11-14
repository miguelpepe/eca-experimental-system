#include "ECAAvatarSettings.h"

#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

UECAAvatarSettings::UECAAvatarSettings()
{
    MetaHumanClass = FSoftClassPath(TEXT("/Game/MetaHumans/Keiji/BP_Keiji.BP_Keiji_C"));
    FaceAnimationClass = FSoftClassPath(TEXT("/Game/MetaHumans/Common/Face/Face_AnimBP.Face_AnimBP_C"));
    PushToTalkKey = EKeys::SpaceBar;
}

UECAAvatarSettings* UECAAvatarSettings::CreateEffectiveSettings(UObject* Outer, bool bUseLocalProfile)
{
    // read local overrides into a transient copy, never into public defaults
    UECAAvatarSettings* Settings = DuplicateObject<UECAAvatarSettings>(GetDefault<UECAAvatarSettings>(), Outer);
    const FString LocalPath = FPaths::ConvertRelativePathToFull(
        FPaths::ProjectConfigDir() / TEXT("ECA.local.ini"));
    if (bUseLocalProfile && FPaths::FileExists(LocalPath))
    {
        Settings->LoadConfig(StaticClass(), *LocalPath);
    }
    FString Endpoint;
    if (FParse::Value(FCommandLine::Get(), TEXT("ECAEndpoint="), Endpoint))
    {
        Settings->BackendUrl = Endpoint;
    }
    return Settings;
}

FString UECAAvatarSettings::GetWebSocketUrl() const
{
    FString Url = BackendUrl.TrimStartAndEnd();
    if (Url.RemoveFromStart(TEXT("https://"), ESearchCase::IgnoreCase))
    {
        Url = TEXT("wss://") + Url;
    }
    else if (Url.RemoveFromStart(TEXT("http://"), ESearchCase::IgnoreCase))
    {
        Url = TEXT("ws://") + Url;
    }
    else if (!Url.Contains(TEXT("://")))
    {
        Url = TEXT("ws://") + Url;
    }
    while (Url.EndsWith(TEXT("/"))) { Url.LeftChopInline(1); }
    if (!Url.EndsWith(TEXT("/ws"))) { Url += TEXT("/ws"); }
    return Url;
}
