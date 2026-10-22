package dev.kopybook;

import dev.kopybook.codec.FieldCodec;
import dev.kopybook.codec.FieldException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import java.math.BigInteger;
import java.util.HexFormat;

import static org.junit.jupiter.api.Assertions.*;

/** Same hand-written known-answer vectors as python/tests/test_fields.py. */
class FieldCodecTest {
    static byte[] h(String s) { return HexFormat.of().parseHex(s); }

    @ParameterizedTest
    @CsvSource({"123,true,123C", "-123,true,123D", "123,false,123F", "1234,true,01234C", "-1,true,1D",
            "-123450,true,000123450D", "9999999999999999999999999999999,true,9999999999999999999999999999999C"})
    void packed(String v, boolean signed, String hex) {
        byte[] b = h(hex);
        assertEquals(new BigInteger(v), FieldCodec.packed(b, 0, b.length));
        assertArrayEquals(b, FieldCodec.encodePacked(new BigInteger(v), signed, b.length));
    }

    @Test
    void packedInvalid() {
        assertThrows(FieldException.class, () -> FieldCodec.packed(h("1235"), 0, 2));
        assertThrows(FieldException.class, () -> FieldCodec.packed(h("1A3C"), 0, 2));
    }

    @ParameterizedTest
    @CsvSource({"123,3,false,false,false,F1F2F3", "123,3,true,false,false,F1F2C3", "-123,3,true,false,false,F1F2D3",
            "-123,3,true,true,false,D1F2F3", "-123,3,true,false,true,F1F2F360", "123,3,true,true,true,4EF1F2F3"})
    void zoned(String v, int digits, boolean signed, boolean leading, boolean sep, String hex) {
        byte[] b = h(hex);
        assertEquals(new BigInteger(v), FieldCodec.zoned(b, 0, b.length, signed, leading, sep));
        assertArrayEquals(b, FieldCodec.encodeZoned(new BigInteger(v), digits, signed, leading, sep));
    }

    @ParameterizedTest
    @CsvSource({"-1,true,FFFF", "9999,false,270F", "123456789,true,075BCD15", "-2,true,FFFFFFFFFFFFFFFE", "65535,false,FFFF"})
    void binary(String v, boolean signed, String hex) {
        byte[] b = h(hex);
        assertEquals(new BigInteger(v), FieldCodec.binary(b, 0, b.length, signed));
        assertArrayEquals(b, FieldCodec.encodeBinary(new BigInteger(v), signed, b.length));
    }

    @ParameterizedTest
    @CsvSource({"1.0,41100000", "-118.625,C276A000", "0.5,40800000", "256.0,43100000", "1.0,4110000000000000", "1.0,42010000"})
    void hfp(double v, String hex) {
        byte[] b = h(hex);
        assertEquals(v, FieldCodec.hfp(b, 0, b.length));
    }

    @ParameterizedTest
    @CsvSource(value = {"cp037|A|C1", "cp037|[|BA", "cp500|[|4A", "cp037|¢|4A", "cp1140|€|9F", "cp037|¤|9F"}, delimiter = '|')
    void codepages(String cp, String text, String hex) {
        assertEquals(text, FieldCodec.text(h(hex), 0, 1, FieldCodec.charset(cp), "right"));
        assertArrayEquals(h(hex), FieldCodec.encodeText(text, 1, FieldCodec.charset(cp)));
    }
}
