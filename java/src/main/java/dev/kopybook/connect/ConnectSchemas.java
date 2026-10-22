package dev.kopybook.connect;

import dev.kopybook.codec.LType;
import dev.kopybook.codec.RecordDecoder;
import dev.kopybook.copybook.Node;
import org.apache.kafka.connect.data.*;

import java.util.*;

/** Copybook -> Kafka Connect schema, and decoded values -> Struct. Mirrors the Python Avro emitter. */
public final class ConnectSchemas {
    private final RecordDecoder decoder;
    private final String namespace;
    private final Map<Node, Schema> cache = new IdentityHashMap<>();
    private final Schema root;

    private final boolean nullableAll;

    public ConnectSchemas(RecordDecoder decoder, String namespace) {
        this(decoder, namespace, false);
    }

    /** @param nullableAll make every field optional so fields can be added later (Avro default null). */
    public ConnectSchemas(RecordDecoder decoder, String namespace, boolean nullableAll) {
        this.decoder = decoder;
        this.nullableAll = nullableAll;
        this.namespace = namespace == null || namespace.isEmpty() ? null : namespace;
        this.root = struct(decoder.root(), new ArrayList<>(), false);
    }

    public Schema schema() { return root; }

    static String pascal(String name) {
        StringBuilder sb = new StringBuilder();
        for (String part : name.replace('-', '_').split("_")) {
            if (part.isEmpty()) continue;
            sb.append(Character.toUpperCase(part.charAt(0))).append(part.substring(1).toLowerCase(Locale.ROOT));
        }
        String s = sb.length() == 0 ? "Filler" : sb.toString();
        return Character.isDigit(s.charAt(0)) ? "F" + s : s;
    }

    private String fieldName(Node c) {
        return c.isFiller() ? RecordDecoder.fillerName(c) : c.outName();
    }

    private Schema struct(Node node, List<String> path, boolean optional) {
        String name = path.isEmpty() ? pascal(node.name) : String.join("_", path.stream().map(ConnectSchemas::pascal).toList());
        SchemaBuilder b = SchemaBuilder.struct().name(namespace == null ? name : namespace + "." + name);
        boolean all = decoder.options().redefines == dev.kopybook.codec.DecodeOptions.Redefines.ALL;
        for (Node c : node.children()) {
            if (c.redefines() != null && !all) continue;
            if (c.isFiller() && !decoder.options().keepFiller) continue;
            boolean nullable = nullableAll || (all && (c.redefines() != null || c.isRedefined()));
            List<String> p = new ArrayList<>(path);
            p.add(c.isFiller() ? fieldName(c) : c.name);
            b.field(fieldName(c), typeOf(c, p, nullable));
        }
        if (optional) b.optional();
        Schema s = b.build();
        cache.put(node, s);
        return s;
    }

    private Schema typeOf(Node n, List<String> path, boolean optional) {
        if (n.isArray()) {
            Schema item = n.children().isEmpty() ? leaf(n, false) : struct(n, path, false);
            SchemaBuilder a = SchemaBuilder.array(item);
            if (optional) a.optional();
            return a.build();
        }
        return n.children().isEmpty() ? leaf(n, optional) : struct(n, path, optional);
    }

    private Schema leaf(Node n, boolean optional) {
        LType t = decoder.type(n);
        SchemaBuilder b = switch (t.kind()) {
            case STRING -> SchemaBuilder.string();
            case INT -> SchemaBuilder.int32();
            case LONG -> SchemaBuilder.int64();
            case DOUBLE -> SchemaBuilder.float64();
            case DECIMAL -> Decimal.builder(t.scale()).parameter("connect.decimal.precision", String.valueOf(t.precision()));
        };
        if (optional) b.optional();
        return b.build();
    }

    /** Decoded map -> Struct (recursively). */
    public Struct toStruct(Map<String, Object> value) {
        return (Struct) convert(root, value);
    }

    @SuppressWarnings("unchecked")
    private Object convert(Schema s, Object v) {
        if (v == null) return null;
        switch (s.type()) {
            case STRUCT -> {
                Struct st = new Struct(s);
                Map<String, Object> m = (Map<String, Object>) v;
                for (Field f : s.fields()) st.put(f, convert(f.schema(), m.get(f.name())));
                return st;
            }
            case ARRAY -> {
                List<Object> out = new ArrayList<>();
                for (Object x : (List<Object>) v) out.add(convert(s.valueSchema(), x));
                return out;
            }
            default -> {
                return v;
            }
        }
    }

    /** Struct -> plain map (for the encoder). */
    public static Map<String, Object> toMap(Struct s) {
        Map<String, Object> out = new LinkedHashMap<>();
        for (Field f : s.schema().fields()) out.put(f.name(), plain(s.get(f)));
        return out;
    }

    private static Object plain(Object v) {
        if (v instanceof Struct st) return toMap(st);
        if (v instanceof List<?> l) {
            List<Object> out = new ArrayList<>();
            for (Object x : l) out.add(plain(x));
            return out;
        }
        return v;
    }
}
