package dev.kopybook;

import dev.kopybook.copybook.CopybookException;
import dev.kopybook.copybook.CopybookParser;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/** Hardening: COPY path traversal / symlink escape and the record-length cap. */
class SecurityTest {
    static final String SECRET = "TOP-SECRET-CONTENT-4f2a";

    @TempDir Path tmp;
    Path lib, outside;

    @BeforeEach
    void setUp() throws Exception {
        lib = Files.createDirectory(tmp.resolve("lib"));
        outside = Files.createDirectory(tmp.resolve("outside"));
        Files.writeString(outside.resolve("secret.cpy"), SECRET + "\n");
        Files.writeString(outside.resolve("secret"), SECRET + "\n");
        Files.writeString(lib.resolve("GOOD.cpy"), "           05  A PIC X(3).\n");
    }

    private int copy(String stmt) {
        return CopybookParser.parse("       01  R.\n           " + stmt + "\n", CopybookParser.Format.AUTO, List.of(lib))
                .record(null).size();
    }

    private CopybookException rejects(String stmt, String expect) {
        CopybookException e = assertThrows(CopybookException.class, () -> copy(stmt));
        assertTrue(e.getMessage().contains(expect), e.getMessage());
        assertFalse(e.getMessage().contains(SECRET), e.getMessage());
        return e;
    }

    @ParameterizedTest
    @ValueSource(strings = {"COPY '../outside/secret'.", "COPY '../../etc/hostname'.", "COPY '..'.", "COPY 'a/b'.",
            "COPY '..\\outside\\secret'.", "COPY 'sub\\x'.", "COPY '/etc/hostname'.", "COPY GOOD OF '../outside'."})
    void traversalNamesRejected(String stmt) {
        rejects(stmt, "not a plain member name");
    }

    @Test
    void absolutePathRejected() {
        rejects("COPY '/etc/passwd'.", "not a plain member name");
    }

    @Test
    void symlinkEscapeRejected() throws Exception {
        Files.createSymbolicLink(lib.resolve("LEAK.cpy"), outside.resolve("secret.cpy"));
        rejects("COPY LEAK.", "outside the copy library");
    }

    @Test
    void symlinkedLibraryDirEscapeRejected() throws Exception {
        Files.createSymbolicLink(lib.resolve("evil"), outside);
        rejects("COPY SECRET OF EVIL.", "outside the copy library");
    }

    @Test
    void symlinkInsideLibraryAllowed() throws Exception {
        Files.createSymbolicLink(lib.resolve("ALIAS.cpy"), lib.resolve("GOOD.cpy"));
        assertEquals(3, copy("COPY ALIAS."));
    }

    @Test
    void extensionlessFileNotMatched() throws Exception {
        Files.writeString(lib.resolve("BARE"), "           05  B PIC X.\n");
        rejects("COPY BARE.", "not found");
    }

    @Test
    void errorMessageDoesNotLeakContent() throws Exception {
        Path deep = Files.createDirectories(tmp.resolve("a/b"));
        Files.writeString(tmp.resolve("hostname"), SECRET + "\n");
        CopybookException e = assertThrows(CopybookException.class, () ->
                CopybookParser.parse("       01  R.\n           COPY '../../hostname'.\n", CopybookParser.Format.AUTO, List.of(deep)));
        assertFalse(e.getMessage().contains(SECRET), e.getMessage());
    }

    @Test
    void normalCopyStillWorks() throws Exception {
        assertEquals(3, copy("COPY GOOD."));
        assertEquals(3, copy("COPY good."));
        Files.createDirectory(lib.resolve("sub"));
        Files.writeString(lib.resolve("sub/M.cpy"), "           05  A PIC X(2).\n");
        assertEquals(2, copy("COPY M OF SUB."));
    }

    // ------------------------------------------------------------------ record cap

    private static void parse(String body) {
        CopybookParser.parse("       01  R.\n" + body);
    }

    @Test
    void picAtCapOk() {
        assertEquals(1_000_000, CopybookParser.MAX_RECORD_LENGTH);
        assertEquals(CopybookParser.MAX_RECORD_LENGTH, CopybookParser.parse(
                "       01  R.\n           05  A PIC X(" + CopybookParser.MAX_RECORD_LENGTH + ").\n").record(null).size());
    }

    @ParameterizedTest
    @ValueSource(strings = {"1000001", "999999999", "2147483648", "1000000000000000000000000000000"})
    void hugePicXRejected(String n) {
        CopybookException e = assertThrows(CopybookException.class, () -> parse("           05  A PIC X(" + n + ").\n"));
        assertTrue(e.getMessage().contains("maximum"), e.getMessage());
    }

    @Test
    void recordTotalOverCapRejected() {
        CopybookException e = assertThrows(CopybookException.class, () ->
                parse("           05  A PIC X(600000).\n           05  B PIC X(600000).\n"));
        assertTrue(e.getMessage().contains("maximum record length"), e.getMessage());
    }

    @Test
    void occursOverCapRejected() {
        CopybookException e = assertThrows(CopybookException.class, () ->
                parse("           05  A PIC X(1000) OCCURS 2000 TIMES.\n"));
        assertTrue(e.getMessage().contains("maximum record length"), e.getMessage());
    }
}
