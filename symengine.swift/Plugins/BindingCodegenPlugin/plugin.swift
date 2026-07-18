import Foundation
import PackagePlugin

/// Render into SwiftPM's plugin work directory so source checkouts remain
/// clean. A copied wrapper checkout supplies BINDING_CODEGEN_ROOT explicitly.
@main
struct BindingCodegenPlugin: BuildToolPlugin {
    func createBuildCommands(context: PluginContext, target: Target) throws -> [Command] {
        let root = ProcessInfo.processInfo.environment["BINDING_CODEGEN_ROOT"]
            ?? context.package.directoryURL.deletingLastPathComponent().path
        let spec = URL(fileURLWithPath: root).appendingPathComponent("binding-spec/api.yaml").path
        guard FileManager.default.fileExists(atPath: spec) else {
            throw CodegenError.missingRoot(root)
        }
        let artifact: String
        switch target.name {
        case "SymEngine":
            artifact = "api"
        case "SymEngineTests":
            artifact = "tests"
        default: return []
        }
        let python = ProcessInfo.processInfo.environment["BINDING_CODEGEN_PYTHON"]
        let executable = python ?? "/usr/bin/env"
        let commandArguments = (python == nil ? ["python3"] : []) +
            ["-m", "tools.binding_codegen", "generate", "--language", "swift",
             "--artifact", artifact, "--output", context.pluginWorkDirectoryURL.path]
        return [.prebuildCommand(
            displayName: "Generate shared SymEngine Swift bindings",
            executable: URL(fileURLWithPath: executable),
            arguments: commandArguments,
            environment: ["PYTHONPATH": root,
                          "PATH": ProcessInfo.processInfo.environment["PATH"] ?? "/usr/bin:/bin"],
            outputFilesDirectory: context.pluginWorkDirectoryURL
        )]
    }
}

enum CodegenError: Error, CustomStringConvertible {
    case missingRoot(String)
    var description: String {
        switch self {
        case let .missingRoot(root):
            return "binding-spec/api.yaml was not found below \(root); set BINDING_CODEGEN_ROOT"
        }
    }
}
