// swift-tools-version: 6.0

import Foundation
import PackageDescription

let environment = ProcessInfo.processInfo.environment
let symengineSourceDirectory = environment["SYMENGINE_SOURCE_DIR"] ?? "../symengine"
let symengineBuildDirectory = environment["SYMENGINE_BUILD_DIR"] ?? "../build-swift/symengine"
let symengineLibraryDirectory = environment["SYMENGINE_LIBRARY_DIR"]
    ?? "\(symengineBuildDirectory)/symengine"
let bindingGeneratedDirectory = environment["SYMENGINE_BINDING_GENERATED_DIR"]
    ?? ".build/binding-generated"

let package = Package(
    name: "SymEngine",
    products: [
        .library(name: "SymEngine", targets: ["SymEngine"]),
    ],
    targets: [
        .target(
            name: "CSymEngineSwift",
            publicHeadersPath: "include",
            cxxSettings: [
                .unsafeFlags([
                    "-I\(symengineSourceDirectory)",
                    "-I\(symengineBuildDirectory)",
                    "-I\(bindingGeneratedDirectory)",
                ]),
            ],
            linkerSettings: [
                .unsafeFlags([
                    "-L\(symengineLibraryDirectory)",
                    "-Xlinker", "-rpath",
                    "-Xlinker", symengineLibraryDirectory,
                ]),
                .linkedLibrary("symengine"),
                .linkedLibrary("gmp"),
            ]
        ),
        .target(
            name: "SymEngine",
            dependencies: ["CSymEngineSwift"],
            plugins: ["BindingCodegenPlugin"]
        ),
        .testTarget(
            name: "SymEngineTests",
            dependencies: ["SymEngine"],
            plugins: ["BindingCodegenPlugin"]
        ),
        .plugin(name: "BindingCodegenPlugin", capability: .buildTool(), path: "Plugins/BindingCodegenPlugin"),
    ],
    cxxLanguageStandard: .cxx17
)
