package dev.kopybook.codec;

/** Invalid bytes for a field (bad packed nibble, bad zone, overflow...). */
public class FieldException extends RuntimeException {
    public FieldException(String message) {
        super(message);
    }
}
