package org.symengine;

/** Unchecked exception translated from a SymEngine C++ exception. */
public final class SymEngineException extends RuntimeException {
    SymEngineException(String message) {
        super(message);
    }
}
