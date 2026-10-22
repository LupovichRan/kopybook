package dev.kopybook.codec;

/** Record-level decode failure with the field path and byte offset. */
public class DecodeException extends RuntimeException {
    private final String path;
    private final int offset;

    public DecodeException(String path, int offset, String message) {
        super(path + " @ offset " + offset + ": " + message);
        this.path = path;
        this.offset = offset;
    }

    public String path() { return path; }
    public int offset() { return offset; }
}
