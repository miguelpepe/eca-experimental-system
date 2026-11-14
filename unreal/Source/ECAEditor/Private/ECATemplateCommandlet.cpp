#include "ECATemplateCommandlet.h"

#include "ECAAvatarSession.h"
#include "ECAAvatarGameMode.h"
#include "FileHelpers.h"
#include "Engine/DirectionalLight.h"
#include "Engine/SkyLight.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Engine/Level.h"
#include "GameFramework/WorldSettings.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/FileManager.h"

UECATemplateCommandlet::UECATemplateCommandlet()
{
    IsClient = false;
    IsServer = false;
    IsEditor = true;
    LogToConsole = true;
}

int32 UECATemplateCommandlet::Main(const FString& Params)
{
    const FString MapPath = TEXT("/Game/ECA/ECA_Demo");
    if (!FPackageName::DoesPackageExist(MapPath))
    {
        UWorld* World = UEditorLoadingAndSavingUtils::NewBlankMap(false);
        if (!World) { return 1; }
        World->GetWorldSettings()->DefaultGameMode = AECAAvatarGameMode::StaticClass();
        World->SpawnActor<AECAAvatarSession>();

        AStaticMeshActor* Floor = World->SpawnActor<AStaticMeshActor>();
        Floor->SetActorLabel(TEXT("Stage"));
        Floor->GetStaticMeshComponent()->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,
            TEXT("/Engine/BasicShapes/Plane.Plane")));
        Floor->SetActorScale3D(FVector(10.0, 10.0, 1.0));

        ADirectionalLight* Light = World->SpawnActor<ADirectionalLight>();
        Light->SetActorRotation(FRotator(-35.0, 145.0, 0.0));
        Cast<UDirectionalLightComponent>(Light->GetLightComponent())->SetIntensity(4.0f);
        ASkyLight* Sky = World->SpawnActor<ASkyLight>();
        Sky->GetLightComponent()->SetIntensity(1.0f);
        if (!UEditorLoadingAndSavingUtils::SaveMap(World, MapPath)) { return 1; }
    }

    // local map preference is stored only in the ignored editor config
    const FString ProfilePath = FPaths::ProjectConfigDir() / TEXT("ECA.local.ini");
    FConfigFile Profile;
    FString LocalMap;
    Profile.Read(ProfilePath);
    if (Profile.GetString(TEXT("ECA.Local"), TEXT("StartupMap"), LocalMap) &&
        FPackageName::DoesPackageExist(LocalMap))
    {
        const FString ObjectPath = LocalMap + TEXT(".") + FPackageName::GetShortName(LocalMap);
        const FString EditorDir = FPaths::ProjectSavedDir() / TEXT("Config/WindowsEditor");
        IFileManager::Get().MakeDirectory(*EditorDir, true);
        const FString EditorPath = FPaths::ConvertRelativePathToFull(EditorDir / TEXT("Engine.ini"));
        FConfigFile EditorConfig;
        EditorConfig.Read(EditorPath);
        EditorConfig.SetString(TEXT("/Script/EngineSettings.GameMapsSettings"), TEXT("EditorStartupMap"), *ObjectPath);
        FString LocalGameMode;
        if (Profile.GetString(TEXT("ECA.Local"), TEXT("GameMode"), LocalGameMode))
        {
            EditorConfig.SetString(TEXT("/Script/EngineSettings.GameMapsSettings"), TEXT("GlobalDefaultGameMode"), *LocalGameMode);
            GConfig->SetString(TEXT("/Script/EngineSettings.GameMapsSettings"), TEXT("GlobalDefaultGameMode"), *LocalGameMode, GEngineIni);
        }
        FString ConfigText;
        EditorConfig.WriteToString(ConfigText);
        if (!FFileHelper::SaveStringToFile(ConfigText, *EditorPath)) { return 1; }
        GConfig->SetString(TEXT("/Script/EngineSettings.GameMapsSettings"), TEXT("EditorStartupMap"), *ObjectPath, GEngineIni);
        UE_LOG(LogTemp, Display, TEXT("ECA_LOCAL_MAP: %s"), *LocalMap);
    }
    UE_LOG(LogTemp, Display, TEXT("ECA_TEMPLATE_OK: %s"), *MapPath);
    return 0;
}
