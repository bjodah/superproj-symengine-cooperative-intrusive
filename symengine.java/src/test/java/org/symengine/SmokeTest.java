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
        try (Basic x = SymEngine.symbol("x");
             Basic two = SymEngine.integer(2);
             Basic three = SymEngine.integer(3);
             Basic five = SymEngine.add(two, three);
             Basic product = SymEngine.mul(two, x);
             Basic zero = SymEngine.zero();
             Basic one = SymEngine.one();
             Basic pi = SymEngine.pi();
             Basic difference = SymEngine.sub(three, two);
             Basic quotient = SymEngine.div(three, two);
             Basic power = SymEngine.pow(two, three);
             Basic negative = SymEngine.neg(two);
             Basic sine = SymEngine.sin(x);
             Basic equalProduct = SymEngine.mul(two, x);
             Basic hashedProduct = SymEngine.mul(two, x)) {
            assert zero.toString().equals("0");
            assert one.toString().equals("1");
            assert pi.toString().equals("pi");
            assert five.toString().equals("5");
            assert difference.toString().equals("1");
            assert quotient.toString().equals("3/2");
            assert power.toString().equals("8");
            assert negative.toString().equals("-2");
            assert sine.toString().equals("sin(x)");
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
