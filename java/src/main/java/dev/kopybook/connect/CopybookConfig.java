package dev.kopybook.connect;

import dev.kopybook.codec.DecodeOptions;
import dev.kopybook.codec.RecordDecoder;
import dev.kopybook.codec.RecordEncoder;
import dev.kopybook.copybook.CopybookParser;
import dev.kopybook.copybook.Node;
import org.apache.kafka.common.config.AbstractConfig;
import org.apache.kafka.common.config.ConfigDef;
import org.apache.kafka.common.config.ConfigException;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

/** Shared configuration for the converter and the SMT. */
public final class CopybookConfig extends AbstractConfig {
    public static final String COPYBOOK_PATH = "copybook.path";
    public static final String COPYBOOK_TEXT = "copybook.text";
    public static final String RECORD = "copybook.record";
    public static final String SOURCE_FORMAT = "copybook.source.format";
    public static final String CODEPAGE = "codepage";
    public static final String TRIM = "string.trim";
    public static final String REDEFINES = "redefines.strategy";
    public static final String REDEFINES_WHEN = "redefines.when";
    public static final String INCLUDE_PATH = "copybook.include.path";
    public static final String KEEP_FILLER = "filler.keep";
    public static final String TRUNC = "binary.trunc";
    public static final String FRAMING = "framing";
    public static final String NAMESPACE = "schema.namespace";
    public static final String ALLOW_TRAILING = "allow.trailing.bytes";
    public static final String ON_ERROR = "on.error";
    public static final String NULLABLE_ALL = "schema.nullable.all";

    public static final ConfigDef DEF = new ConfigDef()
            .define(COPYBOOK_PATH, ConfigDef.Type.STRING, "", ConfigDef.Importance.HIGH, "Path to the copybook file on every worker.")
            .define(COPYBOOK_TEXT, ConfigDef.Type.STRING, "", ConfigDef.Importance.HIGH, "Copybook source inline (alternative to copybook.path).")
            .define(RECORD, ConfigDef.Type.STRING, "", ConfigDef.Importance.MEDIUM, "01-level record to use; default is the first.")
            .define(SOURCE_FORMAT, ConfigDef.Type.STRING, "auto", ConfigDef.ValidString.in("auto", "fixed", "free"), ConfigDef.Importance.LOW, "Copybook source format.")
            .define(CODEPAGE, ConfigDef.Type.STRING, "cp037", ConfigDef.Importance.HIGH, "EBCDIC code page: cp037, cp1140, cp500, cp273, cp1047, or any Java charset name.")
            .define(TRIM, ConfigDef.Type.STRING, "right", ConfigDef.ValidString.in("right", "both", "none"), ConfigDef.Importance.LOW, "Trailing/leading space handling for PIC X.")
            .define(REDEFINES_WHEN, ConfigDef.Type.STRING, "", ConfigDef.Importance.MEDIUM, "REDEFINES view selection, e.g. PAYMENT-DATA=IS-PAYMENT,NOTE-DATA=REC-TYPE:N|X. A view with a rule is decoded only when its 88-level (or FIELD:VALUES) holds; views without a rule are the fallback when no rule in the group matches; the rest are null.")
            .define(INCLUDE_PATH, ConfigDef.Type.LIST, "", ConfigDef.Importance.MEDIUM, "Directories searched for COPY members, in order. The directory of copybook.path is always searched last.")
            .define(REDEFINES, ConfigDef.Type.STRING, "all", ConfigDef.ValidString.in("all", "first"), ConfigDef.Importance.MEDIUM, "all = every REDEFINES view as an optional field (null when unreadable); first = only the original item.")
            .define(KEEP_FILLER, ConfigDef.Type.BOOLEAN, false, ConfigDef.Importance.LOW, "Emit FILLER items as filler_<offset> fields.")
            .define(TRUNC, ConfigDef.Type.STRING, "std", ConfigDef.ValidString.in("std", "bin"), ConfigDef.Importance.LOW, "COMP/COMP-4 range: std = PIC digits, bin = full storage.")
            .define(FRAMING, ConfigDef.Type.STRING, "none", ConfigDef.ValidString.in("none", "rdw"), ConfigDef.Importance.MEDIUM, "rdw = each message starts with a 4-byte IBM record descriptor word.")
            .define(NAMESPACE, ConfigDef.Type.STRING, "", ConfigDef.Importance.LOW, "Namespace prefix for struct schema names.")
            .define(ALLOW_TRAILING, ConfigDef.Type.BOOLEAN, false, ConfigDef.Importance.LOW, "Accept bytes after the end of the record.")
            .define(NULLABLE_ALL, ConfigDef.Type.BOOLEAN, false, ConfigDef.Importance.MEDIUM, "Make every field optional (null default) so the copybook can gain fields without breaking BACKWARD compatibility.")
            .define(ON_ERROR, ConfigDef.Type.STRING, "fail", ConfigDef.ValidString.in("fail", "skip"), ConfigDef.Importance.MEDIUM, "SMT only: fail the task, or drop the record (use the DLQ via errors.tolerance for the converter).");

    final Node record;
    final DecodeOptions options;
    final RecordDecoder decoder;
    final RecordEncoder encoder;
    final ConnectSchemas schemas;
    final boolean rdw;
    final boolean skipOnError;

    public CopybookConfig(Map<?, ?> props) {
        super(DEF, props);
        String path = getString(COPYBOOK_PATH), text = getString(COPYBOOK_TEXT);
        java.util.List<Path> copyPaths = new java.util.ArrayList<>();
        for (String d : getList(INCLUDE_PATH)) if (!d.isBlank()) copyPaths.add(Path.of(d.strip()));
        if (!path.isEmpty()) {
            Path parent = Path.of(path).toAbsolutePath().getParent();
            if (parent != null) copyPaths.add(parent);
        }
        if (path.isEmpty() == text.isEmpty())
            throw new ConfigException("set exactly one of " + COPYBOOK_PATH + " or " + COPYBOOK_TEXT);
        if (!path.isEmpty()) {
            try {
                text = Files.readString(Path.of(path), StandardCharsets.UTF_8);
            } catch (IOException e) {
                throw new ConfigException(COPYBOOK_PATH, path, "cannot read copybook: " + e.getMessage());
            }
        }
        CopybookParser.Format fmt = CopybookParser.Format.valueOf(getString(SOURCE_FORMAT).toUpperCase());
        this.record = CopybookParser.parse(text, fmt, copyPaths).record(getString(RECORD));
        this.options = new DecodeOptions().codepage(getString(CODEPAGE)).trim(getString(TRIM))
                .keepFiller(getBoolean(KEEP_FILLER)).trunc(getString(TRUNC)).allowTrailing(getBoolean(ALLOW_TRAILING))
                .redefines(getString(REDEFINES).equals("first") ? DecodeOptions.Redefines.FIRST : DecodeOptions.Redefines.ALL);
        try {
            this.options.redefinesWhen(getString(REDEFINES_WHEN));
            this.decoder = new RecordDecoder(record, options);
        } catch (IllegalArgumentException e) {
            throw new ConfigException(REDEFINES_WHEN, getString(REDEFINES_WHEN), e.getMessage());
        }
        this.encoder = new RecordEncoder(record, options);
        this.schemas = new ConnectSchemas(decoder, getString(NAMESPACE), getBoolean(NULLABLE_ALL));
        this.rdw = getString(FRAMING).equals("rdw");
        this.skipOnError = getString(ON_ERROR).equals("skip");
    }

    byte[] unframe(byte[] b) {
        if (!rdw) return b;
        if (b.length < 4) throw new org.apache.kafka.connect.errors.DataException("message shorter than an RDW");
        int len = ((b[0] & 0xFF) << 8) | (b[1] & 0xFF);
        if (len != b.length || b[2] != 0 || b[3] != 0)
            throw new org.apache.kafka.connect.errors.DataException("invalid RDW: length " + len + " for a " + b.length + "-byte message");
        byte[] out = new byte[b.length - 4];
        System.arraycopy(b, 4, out, 0, out.length);
        return out;
    }

    byte[] frame(byte[] b) {
        if (!rdw) return b;
        byte[] out = new byte[b.length + 4];
        out[0] = (byte) ((b.length + 4) >> 8);
        out[1] = (byte) (b.length + 4);
        System.arraycopy(b, 0, out, 4, b.length);
        return out;
    }
}
