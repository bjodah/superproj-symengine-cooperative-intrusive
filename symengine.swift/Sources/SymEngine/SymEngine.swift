import CSymEngineSwift

public struct SymEngineError: Error, CustomStringConvertible, Equatable {
    public let code: Int32
    public let message: String

    public var description: String { message }
}

private func swiftRetain(_ pointer: UnsafeMutableRawPointer?) {
    guard let pointer else { return }
    _ = Unmanaged<AnyObject>.fromOpaque(pointer).retain()
}

private func swiftRelease(_ pointer: UnsafeMutableRawPointer?) {
    guard let pointer else { return }
    Unmanaged<AnyObject>.fromOpaque(pointer).release()
}

private func currentError(_ status: symengine_swift_status) -> SymEngineError {
    let message = symengine_swift_last_error().map(String.init(cString:))
        ?? "unknown SymEngine error"
    return SymEngineError(code: Int32(status.rawValue), message: message)
}

private let initializationError: SymEngineError? = {
    let status = symengine_swift_initialize(swiftRetain, swiftRelease)
    return status == SYMENGINE_SWIFT_OK ? nil : currentError(status)
}()

func ensureInitialized() throws {
    if let initializationError { throw initializationError }
}

func check(_ status: symengine_swift_status) throws {
    guard status == SYMENGINE_SWIFT_OK else {
        throw currentError(status)
    }
}

public class Basic: CustomStringConvertible, Equatable {
    internal let raw: symengine_swift_basic_ref
    fileprivate var hasExternalLifecycle = false

    fileprivate init(raw: symengine_swift_basic_ref) {
        self.raw = raw
    }

    deinit {
        guard hasExternalLifecycle else { return }
        symengine_swift_delete_external(
            raw,
            Unmanaged.passUnretained(self).toOpaque()
        )
    }

    public func string() throws -> String {
        try ensureInitialized()
        var result: UnsafeMutablePointer<CChar>?
        try check(symengine_swift_string(raw, &result))
        guard let result else {
            throw SymEngineError(
                code: Int32(SYMENGINE_SWIFT_RUNTIME_ERROR.rawValue),
                message: "SymEngine returned a null string"
            )
        }
        defer { symengine_swift_string_free(result) }
        return String(cString: result)
    }

    public var description: String {
        (try? string()) ?? "<invalid SymEngine expression>"
    }

    public func isEqual(to other: Basic) throws -> Bool {
        try ensureInitialized()
        var result: Int32 = 0
        try check(symengine_swift_equal(raw, other.raw, &result))
        return result != 0
    }

    public static func == (left: Basic, right: Basic) -> Bool {
        (try? left.isEqual(to: right)) ?? false
    }

    public var isExternallyOwned: Bool {
        symengine_swift_is_external_owned(raw) != 0
    }
}

public final class Symbol: Basic {}
public final class Integer: Basic {}

func adopt(_ owned: symengine_swift_basic_ref?) throws -> Basic {
    try ensureInitialized()
    guard let owned else {
        throw currentError(SYMENGINE_SWIFT_RUNTIME_ERROR)
    }

    let lockStatus = symengine_swift_wrapper_lock()
    guard lockStatus == SYMENGINE_SWIFT_OK else {
        symengine_swift_release_owned(owned)
        throw currentError(lockStatus)
    }
    defer { symengine_swift_wrapper_unlock() }

    if let owner = symengine_swift_external_owner(owned) {
        let existing = Unmanaged<Basic>.fromOpaque(owner).takeUnretainedValue()
        withExtendedLifetime(existing) {
            symengine_swift_release_owned(owned)
        }
        return existing
    }

    let wrapper: Basic
    switch symengine_swift_kind(owned) {
    case SYMENGINE_SWIFT_INTEGER:
        wrapper = Integer(raw: owned)
    case SYMENGINE_SWIFT_SYMBOL:
        wrapper = Symbol(raw: owned)
    default:
        wrapper = Basic(raw: owned)
    }

    let owner = Unmanaged.passUnretained(wrapper).toOpaque()
    let status = symengine_swift_externalize(owned, owner)
    guard status == SYMENGINE_SWIFT_OK else {
        symengine_swift_release_owned(owned)
        throw currentError(status)
    }
    wrapper.hasExternalLifecycle = true

    // externalize() replayed the incoming +1 C++ reference as an ARC retain.
    // Consume that temporary reference, leaving the returned Swift reference.
    withExtendedLifetime(wrapper) {
        symengine_swift_release_owned(owned)
    }
    return wrapper
}

public enum SymEngine {
    public static var version: String {
        String(cString: symengine_swift_version())
    }

    public static func symbol(_ name: String) throws -> Symbol {
        try ensureInitialized()
        let value = try name.withCString { pointer in
            try adopt(symengine_swift_symbol(pointer))
        }
        guard let symbol = value as? Symbol else {
            throw SymEngineError(
                code: Int32(SYMENGINE_SWIFT_RUNTIME_ERROR.rawValue),
                message: "SymEngine symbol factory returned a non-Symbol"
            )
        }
        return symbol
    }

    public static func integer(_ value: Int64) throws -> Integer {
        try ensureInitialized()
        let result = try adopt(symengine_swift_integer(value))
        guard let integer = result as? Integer else {
            throw SymEngineError(
                code: Int32(SYMENGINE_SWIFT_RUNTIME_ERROR.rawValue),
                message: "SymEngine integer factory returned a non-Integer"
            )
        }
        return integer
    }

    static func requireInteger(_ value: Basic) throws -> Integer {
        guard let integer = value as? Integer else {
            throw SymEngineError(
                code: Int32(SYMENGINE_SWIFT_RUNTIME_ERROR.rawValue),
                message: "SymEngine constant factory returned a non-Integer"
            )
        }
        return integer
    }
}
