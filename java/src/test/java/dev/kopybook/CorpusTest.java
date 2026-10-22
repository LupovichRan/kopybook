package dev.kopybook;

import com.fasterxml.jackson.databind.JsonNode;
import dev.kopybook.codec.DecodeOptions;
import dev.kopybook.codec.RecordDecoder;
import dev.kopybook.codec.RecordEncoder;
import dev.kopybook.copybook.Node;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;

import java.util.*;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;

/** The Java decoder must reproduce every golden record produced by the Python toolkit. */
class CorpusTest {

    @Test
    void corpusIsLargeEnough() throws Exception {
        assertTrue(Corpus.manifest().size() >= 30);
    }

    @TestFactory
    Stream<DynamicTest> decodeMatchesGolden() throws Exception {
        return Corpus.manifest().stream().map(c -> DynamicTest.dynamicTest(c.get("case").asText(), () -> {
            Corpus.Case k = Corpus.load(c);
            RecordDecoder d = new RecordDecoder(k.root(), k.options());
            assertEquals(k.expected().size(), k.records().size());
            for (int i = 0; i < k.records().size(); i++) {
                JsonNode got = Corpus.json(d.decode(k.records().get(i)));
                assertEquals(k.expected().get(i), got, k.name() + " record " + i);
            }
        }));
    }

    @TestFactory
    Stream<DynamicTest> reencodeRoundTrip() throws Exception {
        return Corpus.manifest().stream().map(c -> DynamicTest.dynamicTest(c.get("case").asText(), () -> {
            Corpus.Case k = Corpus.load(c);
            boolean redefines = k.root().walk().stream().anyMatch(n -> n.redefines() != null);
            boolean floats = k.root().walk().stream().anyMatch(n -> n.kind() == Node.Kind.FLOAT);
            boolean filler = k.root().walk().stream().anyMatch(Node::isFiller);
            if (redefines || floats) return;
            RecordDecoder d = new RecordDecoder(k.root(), k.options());
            RecordEncoder e = new RecordEncoder(k.root(), k.options());
            for (byte[] r : k.records()) {
                Map<String, Object> v = d.decode(r);
                byte[] back = e.encode(v);
                if (filler) assertEquals(v, d.decode(back));
                else assertArrayEquals(r, back, k.name());
            }
        }));
    }

    @Test
    void redefinesFirstOmitsAlternatives() throws Exception {
        Corpus.Case k = Corpus.load(Corpus.manifest().stream().filter(c -> c.get("case").asText().equals("19_redefines_multi")).findFirst().orElseThrow());
        Map<String, Object> v = new RecordDecoder(k.root(), k.options().redefines(DecodeOptions.Redefines.FIRST)).decode(k.records().get(0));
        assertEquals(Set.of("rec_type", "payment_data", "seq_no"), v.keySet());
    }

    @Test
    void odoOutOfRangeIsReported() throws Exception {
        Corpus.Case k = Corpus.load(Corpus.manifest().stream().filter(c -> c.get("case").asText().equals("14_odo_simple")).findFirst().orElseThrow());
        byte[] bad = k.records().get(0).clone();
        bad[8] = 0;
        bad[9] = 99;
        Exception ex = assertThrows(dev.kopybook.codec.DecodeException.class, () -> new RecordDecoder(k.root(), k.options()).decode(bad));
        assertTrue(ex.getMessage().contains("outside 0..20"), ex.getMessage());
    }
}
