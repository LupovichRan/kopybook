package dev.kopybook.codec;

import dev.kopybook.copybook.Node;

import java.math.BigInteger;

/** Logical output type of an elementary item; mirrors Python kopybook.types.ltype. */
public record LType(Kind kind, int precision, int scale, BigInteger min, BigInteger max, int maxLength) {
    public enum Kind { STRING, INT, LONG, DECIMAL, DOUBLE }

    private static final BigInteger INT_MIN = BigInteger.valueOf(Integer.MIN_VALUE);
    private static final BigInteger INT_MAX = BigInteger.valueOf(Integer.MAX_VALUE);
    private static final BigInteger LONG_MIN = BigInteger.valueOf(Long.MIN_VALUE);
    private static final BigInteger LONG_MAX = BigInteger.valueOf(Long.MAX_VALUE);

    public static LType of(Node n, String trunc) {
        switch (n.kind()) {
            case ALNUM, EDITED:
                return new LType(Kind.STRING, 0, 0, null, null, n.size());
            case FLOAT:
                return new LType(Kind.DOUBLE, 0, 0, null, null, 0);
            default:
                break;
        }
        var p = n.pic();
        BigInteger lo, hi;
        int precision;
        Node.Usage u = n.usage();
        if (u == Node.Usage.NATIVE || (u == Node.Usage.BINARY && "bin".equals(trunc))) {
            int bits = n.size() * 8;
            if (p.signed) {
                lo = BigInteger.ONE.shiftLeft(bits - 1).negate();
                hi = BigInteger.ONE.shiftLeft(bits - 1).subtract(BigInteger.ONE);
            } else {
                lo = BigInteger.ZERO;
                hi = BigInteger.ONE.shiftLeft(bits).subtract(BigInteger.ONE);
            }
            precision = hi.toString().length();
        } else {
            hi = BigInteger.TEN.pow(p.digits).subtract(BigInteger.ONE);
            lo = p.signed ? hi.negate() : BigInteger.ZERO;
            precision = p.digits;
        }
        if (p.scale == 0) {
            if (lo.compareTo(INT_MIN) >= 0 && hi.compareTo(INT_MAX) <= 0) return new LType(Kind.INT, precision, 0, lo, hi, 0);
            if (lo.compareTo(LONG_MIN) >= 0 && hi.compareTo(LONG_MAX) <= 0) return new LType(Kind.LONG, precision, 0, lo, hi, 0);
        }
        return new LType(Kind.DECIMAL, Math.max(Math.max(precision, p.scale), 1), p.scale, lo, hi, 0);
    }
}
