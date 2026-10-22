package dev.kopybook.copybook;

/** A resolved PICTURE string. */
public final class Pic {
    public enum Kind { ALNUM, NUMERIC, EDITED }

    public final String raw;
    public final Kind kind;
    public final int length;
    public final int digits;
    public final int scale;
    public final boolean signed;

    Pic(String raw, Kind kind, int length, int digits, int scale, boolean signed) {
        this.raw = raw;
        this.kind = kind;
        this.length = length;
        this.digits = digits;
        this.scale = scale;
        this.signed = signed;
    }

    static String expand(String raw) {
        StringBuilder sb = new StringBuilder();
        String s = raw.toUpperCase();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (i + 1 < s.length() && s.charAt(i + 1) == '(') {
                int close = s.indexOf(')', i + 2);
                if (close < 0) throw new CopybookException("bad PIC " + raw, 0);
                int n = Integer.parseInt(s.substring(i + 2, close));
                sb.append(String.valueOf(c).repeat(n));
                i = close;
            } else {
                sb.append(c);
            }
        }
        return sb.toString();
    }

    private static boolean onlyChars(String s, String allowed) {
        for (char c : s.toCharArray()) if (allowed.indexOf(c) < 0) return false;
        return true;
    }

    static Pic parse(String raw, int line) {
        String s = expand(raw);
        if (s.contains("N") || s.contains("G"))
            throw new CopybookException.Unsupported("PIC " + raw + ": national/DBCS (N/G) is not supported", line);
        if (s.contains("P"))
            throw new CopybookException.Unsupported("PIC " + raw + ": scaling position P is not supported", line);
        if (s.contains("E"))
            throw new CopybookException.Unsupported("PIC " + raw + ": external floating point is not supported", line);
        if (onlyChars(s, "XA9") && (s.contains("X") || s.contains("A")))
            return new Pic(raw, Kind.ALNUM, s.length(), 0, 0, false);
        if (onlyChars(s, "S9V") && s.contains("9")) {
            long sCount = s.chars().filter(c -> c == 'S').count();
            long vCount = s.chars().filter(c -> c == 'V').count();
            if (sCount > 1 || (sCount == 1 && !s.startsWith("S")) || vCount > 1)
                throw new CopybookException("invalid numeric PIC " + raw, line);
            String body = s.startsWith("S") ? s.substring(1) : s;
            int v = body.indexOf('V');
            String ip = v < 0 ? body : body.substring(0, v);
            String fp = v < 0 ? "" : body.substring(v + 1);
            int digits = ip.length() + fp.length();
            if (digits > 38) throw new CopybookException.Unsupported("PIC " + raw + ": more than 38 digits", line);
            return new Pic(raw, Kind.NUMERIC, digits, digits, fp.length(), s.startsWith("S"));
        }
        if (onlyChars(s, "9Z*.,+-$B0/CRDBV") && (s.contains("9") || s.contains("Z") || s.contains("*"))) {
            return new Pic(raw, Kind.EDITED, s.replace("V", "").length(), 0, 0, false);
        }
        throw new CopybookException("unrecognised PIC " + raw, line);
    }
}
