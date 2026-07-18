package org.symengine;

import java.lang.ref.Cleaner;
import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;

/** A structurally immutable SymEngine expression backed by an ordinary RCP cell. */
public final class Basic implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class Releaser implements Runnable {
        private final AtomicLong handle;

        Releaser(long handle) {
            this.handle = new AtomicLong(handle);
        }

        long get() {
            return handle.get();
        }

        @Override public void run() {
            long value = handle.getAndSet(0);
            if (value != 0) SymEngineJNI.release(value);
        }
    }

    private final Releaser releaser;
    private final Cleaner.Cleanable cleanable;

    private Basic(long handle) {
        if (handle == 0) throw new SymEngineException("native SymEngine call returned a null handle");
        releaser = new Releaser(handle);
        cleanable = CLEANER.register(this, releaser);
    }

    static Basic fromHandle(long handle) {
        return new Basic(handle);
    }

    static long requireHandle(Basic value) {
        Objects.requireNonNull(value, "value");
        long handle = value.releaser.get();
        if (handle == 0) throw new IllegalStateException("Basic has been closed");
        return handle;
    }

    /** Releases the native RCP cell now. Calling this again has no effect. */
    @Override public void close() {
        cleanable.clean();
    }

    @Override public boolean equals(Object other) {
        return other instanceof Basic && SymEngineJNI.equal(requireHandle(this), requireHandle((Basic) other));
    }

    @Override public int hashCode() {
        long value = SymEngineJNI.hash(requireHandle(this));
        return (int) (value ^ (value >>> 32));
    }

    @Override public String toString() {
        byte[] bytes = SymEngineJNI.string(requireHandle(this));
        if (bytes == null) throw new SymEngineException("SymEngine returned no string");
        return new String(bytes, StandardCharsets.UTF_8);
    }

    /** Test/debug helper only; Java wrapper identity has no semantic meaning. */
    public boolean sameInstance(Basic other) {
        return SymEngineJNI.sameInstance(requireHandle(this), requireHandle(other));
    }
}
