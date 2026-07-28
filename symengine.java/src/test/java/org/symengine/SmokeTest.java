package org.symengine;

import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.List;

/** Assert-based smoke and lifecycle test; no JUnit dependency is required. */
public final class SmokeTest {
    private static void eventuallyReleased(long baseline, WeakReference<Basic> reference) throws Exception {
        for (int attempt = 0; attempt < 80; ++attempt) {
            System.gc();
            if (reference.get() == null && SymEngineJNI.liveHandleCount() == baseline) return;
            Thread.sleep(25);
        }
        throw new AssertionError("Cleaner did not release the native handle");
    }

    public static void main(String[] arguments) throws Exception {
        // Arithmetic, constant and string expectations live in
        // binding-spec/test-cases.yaml and run from the generated
        // SharedCasesTest.  What remains here is what that shared schema
        // cannot express: the hand-written factories, structural
        // equals/hashCode, and the Java-only handle lifecycle.
        try (Basic x = SymEngine.symbol("x");
             Basic two = SymEngine.integer(2);
             Basic product = SymEngine.mul(two, x);
             Basic equalProduct = SymEngine.mul(two, x);
             Basic hashedProduct = SymEngine.mul(two, x)) {
            assert x.toString().equals("x");
            assert two.toString().equals("2");
            assert product.equals(equalProduct);
            assert product.hashCode() == hashedProduct.hashCode();
        }

        long baseline = SymEngineJNI.liveHandleCount();
        Basic temporary = SymEngine.integer(11);
        temporary.close();
        temporary.close();
        assert SymEngineJNI.liveHandleCount() == baseline;

        Basic collectible = SymEngine.integer(17);
        WeakReference<Basic> reference = new WeakReference<>(collectible);
        collectible = null;
        eventuallyReleased(baseline, reference);

        List<Thread> threads = new ArrayList<>();
        for (int thread = 0; thread < 4; ++thread) {
            Thread worker = new Thread(() -> {
                for (int i = 0; i < 250; ++i) {
                    try (Basic left = SymEngine.integer(i);
                         Basic right = SymEngine.integer(1);
                         Basic value = SymEngine.add(left, right)) {
                        assert value.toString().equals(Integer.toString(i + 1));
                    }
                }
            });
            worker.start();
            threads.add(worker);
        }
        for (Thread worker : threads) worker.join();
        assert SymEngineJNI.liveHandleCount() == baseline;
    }
}
