package dev.kopybook;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import dev.kopybook.connect.CopybookConverter;
import dev.kopybook.connect.CopybookDecode;
import io.confluent.connect.avro.AvroConverter;
import io.confluent.connect.avro.AvroData;
import io.confluent.kafka.schemaregistry.CompatibilityChecker;
import io.confluent.kafka.schemaregistry.CompatibilityLevel;
import io.confluent.kafka.schemaregistry.avro.AvroSchema;
import io.confluent.kafka.schemaregistry.ParsedSchema;
import org.apache.kafka.connect.data.*;
import org.apache.kafka.connect.errors.DataException;
import org.apache.kafka.connect.source.SourceRecord;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.TestFactory;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;

class ConnectTest {

    static Map<String, Object> props(Corpus.Case k) {
        Map<String, Object> p = new HashMap<>();
        p.put("copybook.path", k.copybook().toString());
        p.put("copybook.record", k.record());
        p.put("copybook.include.path", Corpus.DIR.resolve("copybooks/copylib").toString());
        p.put("codepage", k.codepage());
        p.put("schema.namespace", "kopybook.corpus");
        return p;
    }

    static Corpus.Case load(String name) throws Exception {
        return Corpus.load(Corpus.manifest().stream().filter(c -> c.get("case").asText().equals(name)).findFirst().orElseThrow());
    }

    /** Struct -> plain Java (for JSON comparison with the golden files). */
    static Object plain(Object v) {
        if (v instanceof Struct s) {
            Map<String, Object> m = new LinkedHashMap<>();
            for (Field f : s.schema().fields()) m.put(f.name(), plain(s.get(f)));
            return m;
        }
        if (v instanceof List<?> l) return l.stream().map(ConnectTest::plain).toList();
        return v;
    }

    @TestFactory
    Stream<DynamicTest> converterMatchesGolden() throws Exception {
        return Corpus.manifest().stream().map(c -> DynamicTest.dynamicTest(c.get("case").asText(), () -> {
            Corpus.Case k = Corpus.load(c);
            CopybookConverter conv = new CopybookConverter();
            conv.configure(props(k), false);
            for (int i = 0; i < k.records().size(); i++) {
                SchemaAndValue sv = conv.toConnectData("t", k.records().get(i));
                ((Struct) sv.value()).validate();
                assertEquals(k.expected().get(i), Corpus.json(plain(sv.value())), k.name() + " record " + i);
            }
        }));
    }

    /** Connect schema -> Avro (Confluent AvroData) must equal the Python-generated .avsc, ignoring metadata props. */
    @TestFactory
    Stream<DynamicTest> avroSchemaMatchesPython() throws Exception {
        return Corpus.manifest().stream().map(c -> DynamicTest.dynamicTest(c.get("case").asText(), () -> {
            Corpus.Case k = Corpus.load(c);
            CopybookConverter conv = new CopybookConverter();
            conv.configure(props(k), false);
            org.apache.avro.Schema fromJava = new AvroData(100).fromConnectSchema(conv.schema());
            org.apache.avro.Schema fromPython = new org.apache.avro.Schema.Parser()
                    .parse(Files.readString(Corpus.DIR.resolve("schemas").resolve(k.name() + ".avsc")));
            assertEquals(strip(Corpus.M.readTree(fromPython.toString())), strip(Corpus.M.readTree(fromJava.toString())), k.name());
        }));
    }

    static JsonNode strip(JsonNode n) {
        if (n.isObject()) {
            ObjectNode o = Corpus.M.createObjectNode();
            n.fields().forEachRemaining(e -> {
                if (e.getKey().equals("cobol") || e.getKey().startsWith("connect.")) return;
                o.set(e.getKey(), strip(e.getValue()));
            });
            return o;
        }
        if (n.isArray()) {
            var a = Corpus.M.createArrayNode();
            n.forEach(x -> a.add(strip(x)));
            return a;
        }
        return n;
    }

    /** Full path through Confluent's AvroConverter and a mock Schema Registry. */
    @TestFactory
    Stream<DynamicTest> avroConverterRoundTrip() throws Exception {
        return Corpus.manifest().stream().map(c -> DynamicTest.dynamicTest(c.get("case").asText(), () -> {
            Corpus.Case k = Corpus.load(c);
            CopybookConverter conv = new CopybookConverter();
            conv.configure(props(k), false);
            AvroConverter avro = new AvroConverter();
            avro.configure(Map.of("schema.registry.url", "mock://kopybook-" + k.name()), false);
            for (byte[] r : k.records()) {
                SchemaAndValue sv = conv.toConnectData("t", r);
                byte[] wire = avro.fromConnectData("t", sv.schema(), sv.value());
                SchemaAndValue back = avro.toConnectData("t", wire);
                assertEquals(Corpus.json(plain(sv.value())), Corpus.json(plain(back.value())), k.name());
            }
        }));
    }

    @Test
    void converterFromConnectDataRoundTrip() throws Exception {
        Corpus.Case k = load("30_customer_master");
        CopybookConverter conv = new CopybookConverter();
        conv.configure(props(k), false);
        for (byte[] r : k.records()) {
            SchemaAndValue sv = conv.toConnectData("t", r);
            byte[] back = conv.fromConnectData("t", sv.schema(), sv.value());
            assertEquals(Corpus.json(plain(sv.value())), Corpus.json(plain(conv.toConnectData("t", back).value())));
        }
    }

    @Test
    void rdwFraming() throws Exception {
        Corpus.Case k = load("15_odo_group");
        Map<String, Object> p = props(k);
        p.put("framing", "rdw");
        CopybookConverter conv = new CopybookConverter();
        conv.configure(p, false);
        byte[] r = k.records().get(3);
        byte[] framed = new byte[r.length + 4];
        framed[0] = (byte) ((r.length + 4) >> 8);
        framed[1] = (byte) (r.length + 4);
        System.arraycopy(r, 0, framed, 4, r.length);
        assertEquals(k.expected().get(3), Corpus.json(plain(conv.toConnectData("t", framed).value())));
        assertArrayEquals(framed, conv.fromConnectData("t", null, conv.toConnectData("t", framed).value()));
        assertThrows(DataException.class, () -> conv.toConnectData("t", r));
    }

    @Test
    void badBytesBecomeDataException() throws Exception {
        Corpus.Case k = load("09_comp3_packed");
        CopybookConverter conv = new CopybookConverter();
        conv.configure(props(k), false);
        byte[] bad = k.records().get(0).clone();
        bad[4] = 0x05; // invalid sign nibble on P-ODD-S
        DataException e = assertThrows(DataException.class, () -> conv.toConnectData("t", bad));
        assertTrue(e.getMessage().contains("P-ODD-S @ offset 0"), e.getMessage());
        assertThrows(DataException.class, () -> conv.toConnectData("t", Arrays.copyOf(bad, 10)));
    }

    @Test
    void smtValueAndKey() throws Exception {
        Corpus.Case k = load("31_insurance_claim");
        CopybookDecode.Value<SourceRecord> smt = new CopybookDecode.Value<>();
        smt.configure(props(k));
        byte[] r = k.records().get(5);
        SourceRecord in = new SourceRecord(null, null, "claims", 0, Schema.STRING_SCHEMA, "k1", Schema.BYTES_SCHEMA, r);
        SourceRecord out = smt.apply(in);
        assertEquals("k1", out.key());
        assertEquals(Schema.Type.STRUCT, out.valueSchema().type());
        assertEquals(k.expected().get(5), Corpus.json(plain(out.value())));
        // ByteBuffer input and key variant
        CopybookDecode.Key<SourceRecord> key = new CopybookDecode.Key<>();
        key.configure(props(k));
        SourceRecord kin = new SourceRecord(null, null, "claims", 0, Schema.BYTES_SCHEMA, java.nio.ByteBuffer.wrap(r), null, null);
        assertEquals(k.expected().get(5), Corpus.json(plain(key.apply(kin).key())));
        // on.error=skip drops undecodable records
        Map<String, Object> p = props(k);
        p.put("on.error", "skip");
        CopybookDecode.Value<SourceRecord> skip = new CopybookDecode.Value<>();
        skip.configure(p);
        assertNull(skip.apply(new SourceRecord(null, null, "claims", 0, null, null, Schema.BYTES_SCHEMA, new byte[] {1, 2, 3})));
        assertThrows(DataException.class, () -> smt.apply(new SourceRecord(null, null, "claims", 0, null, null, Schema.BYTES_SCHEMA, new byte[] {1, 2, 3})));
    }

    @Test
    void inlineCopybookAndConfigErrors() {
        CopybookConverter conv = new CopybookConverter();
        conv.configure(Map.of("copybook.text", "       01  R.\n           05  A PIC S9(3) COMP-3.\n"), false);
        assertEquals(-123, ((Struct) conv.toConnectData("t", new byte[] {0x12, 0x3D}).value()).get("a"));
        assertThrows(org.apache.kafka.common.config.ConfigException.class, () -> new CopybookConverter().configure(Map.of(), false));
        assertThrows(org.apache.kafka.common.config.ConfigException.class, () -> new CopybookConverter()
                .configure(Map.of("copybook.text", "       01  R.\n           05  A PIC X SYNC.\n"), false));
    }

    // -------------------------------------------------------------- Schema Registry semantics cross-check

    @TestFactory
    Stream<DynamicTest> compatVerdictsMatchSchemaRegistryChecker() throws Exception {
        // The evolution corpus is not part of this repo: point -Dkopybook.pro.compat=<dir> at it to run these checks.
        // Without it, report one visibly skipped test instead of silently generating none.
        String prop = System.getProperty("kopybook.pro.compat", "");
        Path dir = prop.isBlank() ? null : Path.of(prop).normalize();
        if (dir == null || !Files.isDirectory(dir)) {
            return Stream.of(DynamicTest.dynamicTest("evolution corpus not available", () ->
                    Assumptions.assumeTrue(false, "set -Dkopybook.pro.compat=<evolution corpus dir> to run the Schema Registry compat cross-check")));
        }
        List<Path> pairs;
        try (var s = Files.list(dir)) {
            pairs = s.filter(Files::isDirectory).sorted().toList();
        }
        return pairs.stream().map(p -> DynamicTest.dynamicTest(p.getFileName().toString(), () -> {
            JsonNode spec = Corpus.M.readTree(p.resolve("expected.json").toFile());
            boolean nullable = spec.path("options").path("nullable_all").asBoolean(false);
            List<Path> files;
            try (var s = Files.list(p)) {
                files = s.filter(f -> f.toString().endsWith(".cpy")).sorted().toList();
            }
            List<ParsedSchema> schemas = new ArrayList<>();
            for (Path f : files) {
                CopybookConverter conv = new CopybookConverter();
                Map<String, Object> props = new HashMap<>();
                props.put("copybook.path", f.toString());
                props.put("schema.nullable.all", nullable);
                conv.configure(props, false);
                schemas.add(new AvroSchema(new AvroData(100).fromConnectSchema(conv.schema())));
            }
            ParsedSchema latest = schemas.get(schemas.size() - 1);
            List<ParsedSchema> previous = new ArrayList<>(schemas.subList(0, schemas.size() - 1));
            // oldest first: for non-transitive levels SR checks only the last (latest) entry
            JsonNode exp = spec.get("expected");
            for (String level : List.of("BACKWARD", "FORWARD", "FULL", "BACKWARD_TRANSITIVE", "FORWARD_TRANSITIVE", "FULL_TRANSITIVE")) {
                if (!exp.has(level)) continue;
                CompatibilityChecker checker = CompatibilityChecker.checker(CompatibilityLevel.forName(level));
                List<String> errs = checker.isCompatible(latest, previous);
                assertEquals(exp.get(level).asBoolean(), errs.isEmpty(), p.getFileName() + " " + level + " " + errs);
            }
        }));
    }
}
