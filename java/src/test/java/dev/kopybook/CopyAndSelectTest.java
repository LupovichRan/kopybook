package dev.kopybook;

import com.fasterxml.jackson.databind.JsonNode;
import dev.kopybook.codec.DecodeException;
import dev.kopybook.codec.DecodeOptions;
import dev.kopybook.codec.RecordDecoder;
import dev.kopybook.connect.CopybookDecode;
import dev.kopybook.copybook.CopybookException;
import dev.kopybook.copybook.CopybookParser;
import dev.kopybook.copybook.Node;
import org.apache.kafka.common.config.ConfigException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

/** COPY/REPLACING expansion and REDEFINES view selection (redefines.when). */
class CopyAndSelectTest {
    static final Path COPYLIB = Corpus.DIR.resolve("copybooks/copylib");

    static Node leaf(Node r, String name) {
        for (Node n : r.walk()) if (n.name.equals(name)) return n;
        throw new AssertionError(name);
    }

    @Test
    void copyReplacingLayout() throws Exception {
        Node r = CopybookParser.parse(Corpus.DIR.resolve("copybooks/41_copy_replacing.cpy"), CopybookParser.Format.AUTO, List.of(COPYLIB)).record(null);
        assertEquals(145, r.size());
        assertEquals(6, leaf(r, "PTY-GROSS").size());
        assertEquals(119, leaf(r, "TRL-STAMP").offset());
        assertNotNull(leaf(r, "SHIP-ZIP"));
    }

    @Test
    void copyWordReplacing() throws Exception {
        Node r = CopybookParser.parse(Corpus.DIR.resolve("copybooks/42_copy_word_replacing.cpy"), CopybookParser.Format.AUTO, List.of(COPYLIB)).record(null);
        List<String> names = new ArrayList<>();
        for (Node c : r.children()) names.add(c.level + ":" + c.name);
        assertEquals(List.of("5:LG-KEY", "5:LG-DEBIT", "5:LG-CREDIT", "5:AMT-CCY"), names);
    }

    @Test
    void copyErrors(@TempDir Path tmp) throws Exception {
        Files.writeString(tmp.resolve("SELF.cpy"), "           COPY SELF.\n");
        Files.writeString(tmp.resolve("M.cpy"), "           05  ID-IN PIC X(3).\n           05  JUNK PIC X.\n");
        List<Path> p = List.of(tmp);
        assertTrue(assertThrows(CopybookException.class, () -> CopybookParser.parse("       01  R.\n           COPY SELF.\n", CopybookParser.Format.AUTO, p)).getMessage().contains("recursive"));
        assertTrue(assertThrows(CopybookException.class, () -> CopybookParser.parse("       01  R.\n           COPY NOPE.\n", CopybookParser.Format.AUTO, p)).getMessage().contains("not found"));
        assertTrue(assertThrows(CopybookException.class, () -> CopybookParser.parse("       01  R.\n           COPY NOPE.\n")).getMessage().contains("no copy library"));
        assertTrue(assertThrows(CopybookException.class, () -> CopybookParser.parse("       01  R.\n           COPY M REPLACING ==A BY B.\n", CopybookParser.Format.AUTO, p)).getMessage().contains("pseudo-text"));
        Node r = CopybookParser.parse("       01  R.\n           COPY M REPLACING TRAILING ==-IN== BY ==-OUT==\n"
                + "                            ==05  JUNK PIC X.== BY ====.\n", CopybookParser.Format.AUTO, p).record(null);
        assertEquals(1, r.children().size());
        assertEquals("ID-OUT", r.children().get(0).name);
    }

    @Test
    void selectOneViewMatchesGolden() throws Exception {
        Corpus.Case k = ConnectTest.load("19_redefines_multi");
        DecodeOptions o = k.options().redefinesWhen("PAYMENT-DATA=IS-PAYMENT,REFUND-DATA=IS-REFUND,NOTE-DATA=REC-TYPE:N");
        RecordDecoder d = new RecordDecoder(k.root(), o);
        Map<String, String> views = Map.of("P", "payment_data", "R", "refund_data", "N", "note_data");
        for (int i = 0; i < k.records().size(); i++) {
            JsonNode got = Corpus.json(d.decode(k.records().get(i))), exp = k.expected().get(i);
            String want = views.get(exp.get("rec_type").asText());
            assertEquals(exp.get(want), got.get(want), k.name() + "#" + i);
            for (String v : views.values()) if (!v.equals(want)) assertTrue(got.get(v).isNull(), v);
        }
    }

    @Test
    void otherwiseViewAndConfigErrors() throws Exception {
        Corpus.Case k = ConnectTest.load("40_occurs_redefines_mix");
        RecordDecoder d = new RecordDecoder(k.root(), k.options().redefinesWhen("MX-TABLE=MX-KIND:T,MX-PAIRS=MX-KIND:P"));
        for (int i = 0; i < k.records().size(); i++) {
            JsonNode got = Corpus.json(d.decode(k.records().get(i)));
            String kind = k.expected().get(i).get("mx_kind").asText();
            assertEquals(kind.equals("T"), !got.get("mx_table").isNull());
            assertEquals(kind.equals("P"), !got.get("mx_pairs").isNull());
            assertEquals(kind.equals("A"), !got.get("mx_area").isNull());
        }
        assertThrows(IllegalArgumentException.class, () -> new RecordDecoder(k.root(), k.options().redefinesWhen("MX-KIND=MX-KIND:T")));
        assertThrows(IllegalArgumentException.class, () -> new RecordDecoder(k.root(), k.options().redefinesWhen("MX-TABLE=NOPE")));
        assertThrows(IllegalArgumentException.class, () -> DecodeOptions.parseWhen("MX-TABLE"));
        Map<String, Object> p = new HashMap<>(ConnectTest.props(k));
        p.put("redefines.when", "MX-TABLE=NOPE");
        try (CopybookDecode.Value<org.apache.kafka.connect.source.SourceRecord> smt = new CopybookDecode.Value<>()) {
            assertThrows(ConfigException.class, () -> smt.configure(p));
        }
    }

    @Test
    void selectedViewIsStrict() {
        Node root = CopybookParser.parse("       01  R.\n           05  K PIC X.\n           05  A PIC X(2).\n           05  B REDEFINES A PIC 99.\n").record(null);
        Charset cp = Charset.forName("IBM037");
        RecordDecoder d = new RecordDecoder(root, new DecodeOptions().redefinesWhen("B=K:N"));
        Map<String, Object> good = d.decode("N12".getBytes(cp));
        assertEquals(12, good.get("b"));
        assertNull(good.get("a"));
        assertNull(d.decode("XAB".getBytes(cp)).get("b"));
        assertThrows(DecodeException.class, () -> d.decode("NAB".getBytes(cp)));
        RecordDecoder bad = new RecordDecoder(root, new DecodeOptions().redefinesWhen("B=A:12"));
        assertTrue(assertThrows(DecodeException.class, () -> bad.decode("N12".getBytes(cp))).getMessage().contains("not decoded before"));
    }
}
