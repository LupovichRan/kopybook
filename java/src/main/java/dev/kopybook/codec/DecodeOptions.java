package dev.kopybook.codec;

import java.nio.charset.Charset;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/** Decoder options; defaults match the Python CLI. */
public final class DecodeOptions {
    public enum Redefines { ALL, FIRST }

    public Charset charset = FieldCodec.charset("cp037");
    public String trim = "right";
    public boolean keepFiller = false;
    public Redefines redefines = Redefines.ALL;
    public String trunc = "std";
    public boolean allowTrailing = false;
    public boolean odoStrict = true;
    /** REDEFINES view selection: view name -> 88-level name or FIELD:V1|V2. Empty = decode every view. */
    public Map<String, String> redefinesWhen = new LinkedHashMap<>();

    /** Parses {@code VIEW=COND,VIEW2=COND2}. */
    public static Map<String, String> parseWhen(String spec) {
        Map<String, String> out = new LinkedHashMap<>();
        if (spec == null) return out;
        for (String it : spec.split(",")) {
            it = it.strip();
            if (it.isEmpty()) continue;
            int eq = it.indexOf('=');
            if (eq <= 0 || eq == it.length() - 1)
                throw new IllegalArgumentException("bad REDEFINES rule '" + it + "': expected VIEW=88-NAME or VIEW=FIELD:VALUE[|VALUE]");
            out.put(it.substring(0, eq).strip().toUpperCase(Locale.ROOT), it.substring(eq + 1).strip());
        }
        return out;
    }

    public DecodeOptions redefinesWhen(String spec) { this.redefinesWhen = parseWhen(spec); return this; }

    public DecodeOptions codepage(String cp) { this.charset = FieldCodec.charset(cp); return this; }
    public DecodeOptions trim(String t) { this.trim = t; return this; }
    public DecodeOptions keepFiller(boolean k) { this.keepFiller = k; return this; }
    public DecodeOptions redefines(Redefines r) { this.redefines = r; return this; }
    public DecodeOptions trunc(String t) { this.trunc = t; return this; }
    public DecodeOptions allowTrailing(boolean a) { this.allowTrailing = a; return this; }
}
