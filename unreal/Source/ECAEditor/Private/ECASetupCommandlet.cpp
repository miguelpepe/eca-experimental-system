#include "ECASetupCommandlet.h"

#include "MetaHumanBackend.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphSchema.h"
#include "Engine/Blueprint.h"
#include "K2Node_CallFunction.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/PackageName.h"
#include "UObject/SavePackage.h"

UECASetupCommandlet::UECASetupCommandlet()
{
    IsClient = false;
    IsServer = false;
    IsEditor = true;
    LogToConsole = true;
}

int32 UECASetupCommandlet::Main(const FString& Params)
{
    if (!FPackageName::DoesPackageExist(TEXT("/Game/MetaHumans/Common/Face/BP_AI_VoiceManager")))
    {
        UE_LOG(LogTemp, Display, TEXT("ECA_SETUP_OK: no legacy local voice manager to update."));
        return 0;
    }
    UBlueprint* Blueprint = LoadObject<UBlueprint>(nullptr,
        TEXT("/Game/MetaHumans/Common/Face/BP_AI_VoiceManager.BP_AI_VoiceManager"));
    if (!Blueprint)
    {
        UE_LOG(LogTemp, Error, TEXT("ECA: voice manager blueprint missing."));
        return 1;
    }

    UFunction* UrlFunction = UMetaHumanBackend::StaticClass()->FindFunctionByName(
        GET_FUNCTION_NAME_CHECKED(UMetaHumanBackend, GetBackendWebSocketUrl));
    if (!UrlFunction)
    {
        UE_LOG(LogTemp, Error, TEXT("ECA: rebuild the project before running setup."));
        return 1;
    }

    TArray<UEdGraph*> Graphs;
    Blueprint->GetAllGraphs(Graphs);
    int32 SocketCount = 0;
    bool bChanged = false;
    for (UEdGraph* Graph : Graphs)
    {
        // copy the list before adding nodes
        const auto Nodes = Graph->Nodes;
        for (UEdGraphNode* Node : Nodes)
        {
            UK2Node_CallFunction* Call = Cast<UK2Node_CallFunction>(Node);
            if (!Call || (Call->FunctionReference.GetMemberName() != TEXT("CreateWebSocket") &&
                Call->FunctionReference.GetMemberName() != TEXT("CreateWebSocketWithHeaders")))
            {
                continue;
            }

            UEdGraphPin* UrlPin = Call->FindPin(TEXT("ServerUrl"));
            if (!UrlPin)
            {
                UE_LOG(LogTemp, Error, TEXT("ECA: socket URL pin missing."));
                return 1;
            }
            ++SocketCount;
            if (!UrlPin->LinkedTo.IsEmpty())
            {
                const UK2Node_CallFunction* Existing = Cast<UK2Node_CallFunction>(
                    UrlPin->LinkedTo[0]->GetOwningNode());
                if (!Existing || Existing->GetTargetFunction() != UrlFunction)
                {
                    UE_LOG(LogTemp, Error, TEXT("ECA: socket URL already has a custom connection; inspect the voice manager."));
                    return 1;
                }
                continue;
            }

            UK2Node_CallFunction* UrlNode = NewObject<UK2Node_CallFunction>(Graph);
            UrlNode->CreateNewGuid();
            UrlNode->SetFromFunction(UrlFunction);
            UrlNode->NodePosX = Call->NodePosX - 320;
            UrlNode->NodePosY = Call->NodePosY + 100;
            Graph->AddNode(UrlNode, false, false);
            UrlNode->AllocateDefaultPins();
            if (!Graph->GetSchema()->TryCreateConnection(UrlNode->GetReturnValuePin(), UrlPin))
            {
                UE_LOG(LogTemp, Error, TEXT("ECA: could not connect the backend URL node."));
                return 1;
            }
            UrlPin->DefaultValue.Reset();
            bChanged = true;
        }
    }

    if (SocketCount == 0)
    {
        UE_LOG(LogTemp, Error, TEXT("ECA: no WebSocket creation node found."));
        return 1;
    }
    if (bChanged)
    {
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
        FKismetEditorUtilities::CompileBlueprint(Blueprint);
        if (Blueprint->Status == BS_Error)
        {
            UE_LOG(LogTemp, Error, TEXT("ECA: voice manager compilation failed."));
            return 1;
        }
        UPackage* Package = Blueprint->GetOutermost();
        const FString Filename = FPackageName::LongPackageNameToFilename(
            Package->GetName(), FPackageName::GetAssetPackageExtension());
        FSavePackageArgs SaveArgs;
        SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
        SaveArgs.SaveFlags = SAVE_NoError;
        if (!UPackage::SavePackage(Package, Blueprint, *Filename, SaveArgs))
        {
            UE_LOG(LogTemp, Error, TEXT("ECA: could not save the voice manager."));
            return 1;
        }
    }
    UE_LOG(LogTemp, Display, TEXT("ECA_SETUP_OK: %d socket(s), endpoint %s, changed=%s"),
        SocketCount, *UMetaHumanBackend::GetBackendWebSocketUrl(), bChanged ? TEXT("true") : TEXT("false"));
    return 0;
}
