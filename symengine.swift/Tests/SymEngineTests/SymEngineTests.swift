import XCTest
@testable import SymEngine

final class SymEngineTests: XCTestCase {
    // The arithmetic, constant and string expectations that used to be
    // repeated here (testSharedAPISmoke/testBasicOperations) now live in
    // binding-spec/test-cases.yaml and are rendered into SharedCasesTests.
    // What remains is what that shared schema cannot express: the
    // hand-written factories (structural comparison stays in
    // testMathematicalEquality below).
    func testManualFactories() throws {
        let x = try SymEngine.symbol("phase0_x")
        let two = try SymEngine.integer(2)

        XCTAssertEqual(try x.string(), "phase0_x")
        XCTAssertEqual(try two.string(), "2")
    }

    func testDynamicWrapperTypesAndExternalOwnership() throws {
        let x = try SymEngine.symbol("x")
        let one = try SymEngine.integer(1)

        XCTAssertTrue(type(of: x) == Symbol.self)
        XCTAssertTrue(type(of: one) == Integer.self)
        XCTAssertTrue(x.isExternallyOwned)
        XCTAssertTrue(one.isExternallyOwned)
    }

    func testCanonicalResultReusesSwiftIdentity() throws {
        let x = try SymEngine.symbol("identity_x")
        let zero = try SymEngine.zero()
        let again = try SymEngine.add(x, zero)

        XCTAssertTrue(x === again)
    }

    func testExpressionRCPRetainsOperandWrapper() throws {
        weak var weakSymbol: Symbol?
        var expression: Basic?

        do {
            let symbol = try SymEngine.symbol("retained_x")
            weakSymbol = symbol
            expression = try SymEngine.add(symbol, SymEngine.one())
        }

        XCTAssertNotNil(weakSymbol)
        XCTAssertEqual(try expression?.string(), "1 + retained_x")
        expression = nil
        XCTAssertNil(weakSymbol)
    }

    func testSingletonIdentityReuse() throws {
        let first = try SymEngine.pi()
        let second = try SymEngine.pi()

        XCTAssertTrue(first === second)
        XCTAssertEqual(try first.string(), "pi")
    }

    func testMathematicalEquality() throws {
        let x1 = try SymEngine.symbol("equal_x")
        let x2 = try SymEngine.symbol("equal_x")
        let y = try SymEngine.symbol("unequal_y")

        XCTAssertTrue(try x1.isEqual(to: x2))
        XCTAssertFalse(try x1.isEqual(to: y))
    }

    func testVersionIsAvailable() {
        XCTAssertFalse(SymEngine.version.isEmpty)
    }
}
