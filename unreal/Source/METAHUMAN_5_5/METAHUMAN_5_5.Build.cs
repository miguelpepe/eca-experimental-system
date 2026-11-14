// Fill out your copyright notice in the Description page of Project Settings.

using UnrealBuildTool;

public class METAHUMAN_5_5 : ModuleRules
{
	public METAHUMAN_5_5(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicIncludePaths.Add(ModuleDirectory);

		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "HTTP", "Json", "JsonUtilities" });

		PublicDependencyModuleNames.AddRange(new string[] { "DeveloperSettings" });
		PrivateDependencyModuleNames.AddRange(new string[] { "WebSockets", "RuntimeAudioImporter", "ACERuntime", "ACECore" });

		// Uncomment if you are using Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });

		// Uncomment if you are using online features
		// PrivateDependencyModuleNames.Add("OnlineSubsystem");

		// To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
	}
}
