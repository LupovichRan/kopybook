package dev.kopybook;

import dev.kopybook.codec.DecodeOptions;
import dev.kopybook.codec.FieldCodec;
import dev.kopybook.codec.FieldException;
import dev.kopybook.codec.RecordDecoder;
import dev.kopybook.codec.RecordEncoder;
import dev.kopybook.copybook.CopybookParser;
import org.junit.jupiter.api.function.Executable;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.charset.Charset;
import java.util.HexFormat;
import java.util.Map;
import java.util.regex.Pattern;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;

/** No field error may echo field data: raw bytes (hex, decimal or as a character) or values. */
class NoRawDataTest {
    static final Charset CP037 = FieldCodec.charset("cp037");

    static byte[] h(String s) { return HexFormat.of().parseHex(s); }

    static RecordDecoder dec(String pic) {
        return new RecordDecoder(CopybookParser.parse("       01  R.\n           05  A  PIC " + pic + ".\n").record(null), new DecodeOptions());
    }

    static RecordEncoder enc(String pic) {
        return new RecordEncoder(CopybookParser.parse("       01  R.\n           05  A  PIC " + pic + ".\n").record(null), new DecodeOptions());
    }

    static void assertNoRaw(String msg, byte[] data, String[] values, String nibbles) {
        String low = msg.toLowerCase();
        if (data.length > 0) assertFalse(low.contains(HexFormat.of().formatHex(data)), msg);
        for (byte b : data) {
            int x = b & 0xFF;
            String hex = String.format("%02x", x);
            // hex pair not inside an ordinary word ("ff" in "offset" is fine, "ff" or "f9f8" is not)
            assertFalse(Pattern.compile("(?<![g-z])" + hex + "(?![g-z])").matcher(low).find(), msg);
            if (x >= 100) assertFalse(msg.contains(Integer.toString(x)), msg);
            String ch = new String(new byte[]{b}, CP037);
            if (!Character.isLetterOrDigit(ch.charAt(0)) && !Character.isWhitespace(ch.charAt(0))) assertFalse(msg.contains(ch), msg);
        }
        for (String v : values) assertFalse(msg.contains(v), msg);
        for (char n : nibbles.toLowerCase().toCharArray())
            assertFalse(Pattern.compile("(?<![0-9a-z])" + n + "(?![0-9a-z])").matcher(low).find(), msg);
    }

    static Arguments a(String name, Executable call, String hex, String nibbles, String... values) {
        return Arguments.of(name, call, h(hex), values, nibbles);
    }

    static Stream<Arguments> decodeSites() {
        return Stream.of(
                a("packed too many digits", () -> FieldCodec.packed(h("98765C"), 0, 3, 4, true), "98765C", "9", "98765"),
                a("packed digit nibble", () -> FieldCodec.packed(h("98765A3C"), 0, 4, 7, true), "98765A3C", "a", "98765"),
                a("packed negative unsigned", () -> FieldCodec.packed(h("98765D"), 0, 3, 5, false), "98765D", "d", "98765"),
                a("packed sign nibble", () -> FieldCodec.packed(h("987657"), 0, 3, 5, true), "987657", "7", "98765"),
                a("separate sign", () -> FieldCodec.zoned(h("F9F8F7F67B"), 0, 5, true, false, true), "F9F8F7F67B", "", "9876"),
                a("separate sign leading", () -> FieldCodec.zoned(h("7BF9F8F7F6"), 0, 5, true, true, true), "7BF9F8F7F6", "", "9876"),
                a("zoned digit nibble", () -> FieldCodec.zoned(h("F9F8F7F6FA"), 0, 5, false, false, false), "F9F8F7F6FA", "a", "9876"),
                a("zoned sign zone", () -> FieldCodec.zoned(h("F9F8F7F679"), 0, 5, true, false, false), "F9F8F7F679", "7", "9876"),
                a("zoned zone nibble", () -> FieldCodec.zoned(h("F939F7F6F5"), 0, 5, false, false, false), "F939F7F6F5", "3", "99765", "9765"),
                a("text not valid", () -> FieldCodec.text(h("C1FA"), 0, 2, Charset.forName("US-ASCII"), "right"), "C1FA", ""),
                a("binary exceeds PIC (record)", () -> dec("S9(4) COMP").decode(h("7FFF")), "7FFF", "", "32767"));
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("decodeSites")
    void decodeErrorsHaveNoRawData(String name, Executable call, byte[] data, String[] values, String nibbles) {
        RuntimeException e = assertThrows(RuntimeException.class, call);
        assertTrue(e instanceof FieldException || e instanceof dev.kopybook.codec.DecodeException, e.toString());
        assertTrue(e.getMessage().contains("-byte field"), e.getMessage());
        assertNoRaw(e.getMessage(), data, values, nibbles);
    }

    static Stream<Arguments> encodeSites() {
        return Stream.of(
                a("packed does not fit", () -> FieldCodec.encodePacked(BigInteger.valueOf(987654), true, 3), "", "", "98765"),
                a("zoned does not fit", () -> FieldCodec.encodeZoned(BigInteger.valueOf(987654), 5, true, false, false), "", "", "98765"),
                a("binary does not fit", () -> FieldCodec.encodeBinary(BigInteger.valueOf(98765), true, 2), "", "", "98765"),
                a("binary does not fit (unsigned negative)", () -> FieldCodec.encodeBinary(BigInteger.valueOf(-98765), false, 4), "", "", "98765"),
                a("binary does not fit (sign bit)", () -> FieldCodec.encodeBinary(BigInteger.valueOf(40000), true, 2), "", "", "40000"),
                a("text too long", () -> FieldCodec.encodeText("SECRETMARKERXYZ", 4, CP037), "", "", "SECRET", "MARKER"),
                a("text not representable", () -> FieldCodec.encodeText("\u20acMARK", 10, CP037), "", "", "\u20ac", "20ac", "MARK"),
                a("record decimals", () -> enc("S9(5)V99").encode(Map.of("a", new BigDecimal("9876.54321"))), "", "", "9876", "54321"),
                a("record packed does not fit", () -> enc("S9(5) COMP-3").encode(Map.of("a", 987654)), "", "", "98765"),
                a("record binary does not fit", () -> enc("S9(4) COMP").encode(Map.of("a", 98765)), "", "", "98765"),
                a("record not a number", () -> enc("S9(4) COMP").encode(Map.of("a", "9876SECRET")), "", "", "9876", "SECRET"));
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("encodeSites")
    void encodeErrorsHaveNoRawData(String name, Executable call, byte[] data, String[] values, String nibbles) {
        FieldException e = assertThrows(FieldException.class, call);
        assertNoRaw(e.getMessage(), data, values, nibbles);
    }
}
