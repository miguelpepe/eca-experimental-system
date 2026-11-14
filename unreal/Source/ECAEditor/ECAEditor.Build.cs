using UnrealBuildTool;

public class ECAEditor : ModuleRules
{
    public ECAEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateDependencyModuleNames.AddRange(new[]
        {
            "Core", "CoreUObject", "Engine", "UnrealEd", "BlueprintGraph",
            "Kismet", "KismetCompiler", "METAHUMAN_5_5"
        });
    }
}
