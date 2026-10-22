package dev.kopybook.copybook;

/** Syntax error or unsupported clause in a copybook. */
public class CopybookException extends RuntimeException {
    private final int line;

    public CopybookException(String message, int line) {
        super(line > 0 ? "line " + line + ": " + message : message);
        this.line = line;
    }

    public int line() {
        return line;
    }

    /** A clause that would change the byte layout and is deliberately not supported. */
    public static class Unsupported extends CopybookException {
        public Unsupported(String message, int line) {
            super(message, line);
        }
    }
}
