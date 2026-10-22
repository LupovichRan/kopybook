package dev.kopybook.codec;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.util.Map;

/** Byte-level codecs for elementary items (IBM Enterprise COBOL semantics). */
public final class FieldCodec {
    static final int EBCDIC_PLUS = 0x4E;
    static final int EBCDIC_MINUS = 0x60;
    private static final Map<String, String> ALIASES = Map.of(
            "cp037", "IBM037", "cp1140", "IBM01140", "cp500", "IBM500", "cp273", "IBM273",
            "cp1047", "IBM1047", "cp1141", "IBM01141", "cp1148", "IBM01148", "cp875", "IBM875");

    private FieldCodec() { }

    public static Charset charset(String name) {
        return Charset.forName(ALIASES.getOrDefault(name.toLowerCase(), name));
    }

    private static boolean pos(int z) { return z == 0xC || z == 0xF || z == 0xA || z == 0xE; }
    private static boolean neg(int z) { return z == 0xD || z == 0xB; }

    private static String hex(byte[] b, int off, int len) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < len; i++) sb.append(String.format("%02x", b[off + i] & 0xFF));
        return sb.toString();
    }

    public static BigInteger packed(byte[] b, int off, int len) {
        long acc = 0;
        BigInteger big = null;
        int nibbles = len * 2 - 1;
        for (int i = 0; i < nibbles; i++) {
            int x = b[off + i / 2] & 0xFF;
            int d = (i % 2 == 0) ? x >> 4 : x & 0xF;
            if (d > 9) throw new FieldException("invalid packed digit nibble " + Integer.toHexString(d).toUpperCase() + " in " + hex(b, off, len));
            if (big == null && acc < 99_999_999_999_999_999L / 10) {
                acc = acc * 10 + d;
            } else {
                if (big == null) big = BigInteger.valueOf(acc);
                big = big.multiply(BigInteger.TEN).add(BigInteger.valueOf(d));
            }
        }
        int sign = b[off + len - 1] & 0xF;
        BigInteger v = big != null ? big : BigInteger.valueOf(acc);
        if (neg(sign)) return v.negate();
        if (pos(sign)) return v;
        throw new FieldException("invalid packed sign nibble " + Integer.toHexString(sign).toUpperCase() + " in " + hex(b, off, len));
    }

    public static BigInteger zoned(byte[] b, int off, int len, boolean signed, boolean leading, boolean separate) {
        boolean negative = false;
        int start = off, end = off + len;
        if (signed && separate) {
            int sc = b[leading ? off : off + len - 1] & 0xFF;
            if (sc == EBCDIC_MINUS) negative = true;
            else if (sc != EBCDIC_PLUS) throw new FieldException("invalid separate sign byte " + String.format("%02X", sc));
            if (leading) start++; else end--;
        }
        long acc = 0;
        BigInteger big = null;
        for (int i = start; i < end; i++) {
            int x = b[i] & 0xFF, zone = x >> 4, d = x & 0xF;
            boolean signPos = leading ? i == start : i == end - 1;
            if (d > 9) throw new FieldException("invalid zoned digit " + String.format("%02X", x) + " in " + hex(b, off, len));
            if (signed && !separate && signPos) {
                if (neg(zone)) negative = true;
                else if (!pos(zone)) throw new FieldException("invalid zoned sign " + String.format("%02X", x) + " in " + hex(b, off, len));
            } else if (zone != 0xF && !(signPos && pos(zone))) {
                throw new FieldException("invalid zoned byte " + String.format("%02X", x) + " in " + hex(b, off, len));
            }
            if (big == null && acc < 99_999_999_999_999_999L / 10) {
                acc = acc * 10 + d;
            } else {
                if (big == null) big = BigInteger.valueOf(acc);
                big = big.multiply(BigInteger.TEN).add(BigInteger.valueOf(d));
            }
        }
        BigInteger v = big != null ? big : BigInteger.valueOf(acc);
        return negative ? v.negate() : v;
    }

    public static BigInteger binary(byte[] b, int off, int len, boolean signed) {
        byte[] slice = new byte[len];
        System.arraycopy(b, off, slice, 0, len);
        return signed ? new BigInteger(slice) : new BigInteger(1, slice);
    }

    public static double hfp(byte[] b, int off, int len) {
        long word = 0;
        for (int i = 0; i < len; i++) word = (word << 8) | (b[off + i] & 0xFF);
        int fracBits = len * 8 - 8;
        boolean negative = (word >>> (len * 8 - 1)) != 0;
        int exp = (int) ((word >>> fracBits) & 0x7F);
        long frac = word & ((1L << fracBits) - 1);
        if (frac == 0) return negative ? -0.0 : 0.0;
        double v = Math.scalb((double) frac, 4 * (exp - 64) - fracBits);
        return negative ? -v : v;
    }

    public static String text(byte[] b, int off, int len, Charset cs, String trim) {
        String s;
        try {
            s = cs.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(b, off, len)).toString();
        } catch (CharacterCodingException e) {
            throw new FieldException("bytes not valid in " + cs.name() + ": " + hex(b, off, len));
        }
        switch (trim) {
            case "right": {
                int e = s.length();
                while (e > 0 && s.charAt(e - 1) == ' ') e--;
                return s.substring(0, e);
            }
            case "both": {
                int st = 0, e = s.length();
                while (e > 0 && s.charAt(e - 1) == ' ') e--;
                while (st < e && s.charAt(st) == ' ') st++;
                return s.substring(st, e);
            }
            default:
                return s;
        }
    }

    // ------------------------------------------------------------------ encoders (for sinks and tests)

    public static byte[] encodePacked(BigInteger u, boolean signed, int size) {
        if (u.signum() < 0 && !signed) throw new FieldException("negative value for unsigned field");
        String s = u.abs().toString();
        int nib = size * 2 - 1;
        if (s.length() > nib) throw new FieldException(u + " does not fit " + size + " packed bytes");
        s = "0".repeat(nib - s.length()) + s;
        int sign = !signed ? 0xF : (u.signum() < 0 ? 0xD : 0xC);
        byte[] out = new byte[size];
        for (int i = 0; i < nib; i++) {
            int d = s.charAt(i) - '0';
            if (i % 2 == 0) out[i / 2] |= (byte) (d << 4); else out[i / 2] |= (byte) d;
        }
        out[size - 1] |= (byte) sign;
        return out;
    }

    public static byte[] encodeZoned(BigInteger u, int digits, boolean signed, boolean leading, boolean separate) {
        if (u.signum() < 0 && !signed) throw new FieldException("negative value for unsigned field");
        String s = u.abs().toString();
        if (s.length() > digits) throw new FieldException(u + " does not fit " + digits + " digits");
        s = "0".repeat(digits - s.length()) + s;
        byte[] body = new byte[digits];
        for (int i = 0; i < digits; i++) body[i] = (byte) (0xF0 | (s.charAt(i) - '0'));
        if (signed && separate) {
            byte[] out = new byte[digits + 1];
            byte sc = (byte) (u.signum() < 0 ? EBCDIC_MINUS : EBCDIC_PLUS);
            if (leading) { out[0] = sc; System.arraycopy(body, 0, out, 1, digits); }
            else { System.arraycopy(body, 0, out, 0, digits); out[digits] = sc; }
            return out;
        }
        if (signed) {
            int idx = leading ? 0 : digits - 1;
            body[idx] = (byte) ((u.signum() < 0 ? 0xD0 : 0xC0) | (body[idx] & 0xF));
        }
        return body;
    }

    public static byte[] encodeBinary(BigInteger u, boolean signed, int size) {
        byte[] raw = u.toByteArray();
        byte[] out = new byte[size];
        byte pad = (byte) (u.signum() < 0 ? 0xFF : 0x00);
        int skip = 0;
        while (raw.length - skip > size && raw[skip] == 0 && !signed) skip++;
        if (raw.length - skip > size || (!signed && u.signum() < 0)) throw new FieldException(u + " does not fit " + size + " bytes");
        if (signed && raw.length == size + 1 && raw[0] == 0) throw new FieldException(u + " does not fit " + size + " bytes");
        java.util.Arrays.fill(out, pad);
        System.arraycopy(raw, skip, out, size - (raw.length - skip), raw.length - skip);
        return out;
    }

    public static byte[] encodeText(String s, int size, Charset cs) {
        byte[] b;
        try {
            b = cs.newEncoder().onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(s)).array();
            b = java.util.Arrays.copyOf(b, cs.encode(s).limit());
        } catch (CharacterCodingException e) {
            throw new FieldException("text not representable in " + cs.name());
        }
        if (b.length > size) throw new FieldException("text longer than " + size);
        byte[] out = new byte[size];
        byte sp = cs.encode(" ").get(0);
        java.util.Arrays.fill(out, sp);
        System.arraycopy(b, 0, out, 0, b.length);
        return out;
    }

    public static BigDecimal scaled(BigInteger unscaled, int scale) {
        return new BigDecimal(unscaled, scale);
    }
}
