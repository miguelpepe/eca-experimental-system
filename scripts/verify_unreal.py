"""Run inside Unreal with scripts/unreal.ps1 -Action Verify."""

import configparser
import json
from pathlib import Path

import unreal


def character_check(actors, use_local=False, override=None):
    session = actors.spawn_actor_from_class(unreal.ECAAvatarSession, unreal.Vector(), transient=True)
    try:
        if override:
            session.set_editor_property("meta_human_blueprint", unreal.load_class(None, override))
        assert session.prepare_character(use_local), session.get_editor_property("status")
        character = session.get_editor_property("character")
        face = next(
            mesh for mesh in character.get_components_by_class(unreal.SkeletalMeshComponent)
            if mesh.get_name() == "Face"
        )
        assert character.get_components_by_class(unreal.ACEAudioCurveSourceComponent)
        assert face.get_editor_property("anim_class").get_path_name().endswith("Face_AnimBP_C")
        return character.get_class().get_path_name()
    finally:
        character = session.get_editor_property("character")
        if character:
            actors.destroy_actor(character)
        actors.destroy_actor(session)


def dependencies(roots):
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(True)
    options = unreal.AssetRegistryDependencyOptions()
    options.set_editor_property("include_hard_package_references", True)
    options.set_editor_property("include_soft_package_references", True)
    found = set()
    pending = list(roots)
    while pending:
        package = pending.pop()
        if package in found or not package.startswith("/Game/"):
            continue
        found.add(package)
        pending.extend(str(name) for name in registry.get_dependencies(package, options))
    return sorted(found)


def verify():
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    assert level.load_level("/Game/ECA/ECA_Demo")
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    assert len(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.ECAAvatarSession)) == 1
    public_character = character_check(actors)
    assert public_character == "/Game/MetaHumans/Keiji/BP_Keiji.BP_Keiji_C", public_character
    alternate_character = character_check(actors, override="/Game/MetaHumans/Ada/BP_Ada.BP_Ada_C")
    assert alternate_character.endswith("BP_Ada_C"), alternate_character
    packages = dependencies([
        "/Game/ECA/ECA_Demo", "/Game/MetaHumans/Keiji/BP_Keiji",
        "/Game/MetaHumans/Ada/BP_Ada", "/Game/MetaHumans/Common/Face/Face_AnimBP",
    ])
    profile = configparser.ConfigParser(interpolation=None)
    profile.read(Path(unreal.Paths.project_config_dir()) / "ECA.local.ini", encoding="utf-8")
    local_character = None
    local_map = None
    if profile.has_section("ECA.Local"):
        private_prefix = profile.get("ECA.Local", "PrivateContent", fallback="")
        if private_prefix:
            assert not any(path.startswith(private_prefix) for path in packages), "Public scene references private content"
            registry = unreal.AssetRegistryHelpers.get_asset_registry()
            options = unreal.AssetRegistryDependencyOptions()
            excluded = {
                "/Game/MetaHumans/Common/Face/BP_AI_VoiceManager",
                "/Game/MetaHumans/Common/Face/audio2face",
                "/Game/MetaHumans/Keiji/no_move",
            }
            offenders = []
            for asset in registry.get_assets_by_path("/Game/MetaHumans", recursive=True):
                package = str(asset.package_name)
                if package in excluded or package.startswith(private_prefix):
                    continue
                if any(str(name).startswith(private_prefix) for name in registry.get_dependencies(package, options)):
                    offenders.append(package)
            assert not offenders, f"Public assets reference private content: {offenders}"
        local_map = profile.get("ECA.Local", "StartupMap", fallback="")
        if local_map:
            assert level.load_level(local_map)
            editor_config = Path(unreal.Paths.project_saved_dir()) / "Config/WindowsEditor/Engine.ini"
            assert f"EditorStartupMap={local_map}." in editor_config.read_text(encoding="utf-8-sig")
        local_character = character_check(actors, use_local=True)
    return {
        "passed": True,
        "engine": unreal.SystemLibrary.get_engine_version(),
        "public_map": "/Game/ECA/ECA_Demo",
        "public_character": public_character,
        "alternate_character": alternate_character,
        "local_map": local_map,
        "local_character": local_character,
        "public_dependencies": packages,
        "scope": "Editor loading, character swaps, face/ACE wiring and asset dependencies; no live speech inference.",
    }


report_path = Path(unreal.Paths.project_saved_dir()) / "Validation" / "eca-project.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
try:
    report = verify()
except Exception as exc:
    report_path.write_text(json.dumps({"passed": False, "error": str(exc)}, indent=2), encoding="utf-8")
    raise
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
unreal.log("ECA_VERIFY_OK " + str(report_path))
