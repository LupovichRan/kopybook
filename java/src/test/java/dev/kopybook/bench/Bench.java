package dev.kopybook.bench;

import dev.kopybook.codec.DecodeOptions;
import dev.kopybook.codec.RecordDecoder;
import dev.kopybook.connect.ConnectSchemas;
import dev.kopybook.copybook.CopybookParser;
import dev.kopybook.copybook.Node;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Single-thread decode throughput: java -cp ... dev.kopybook.bench.Bench ../corpus */
public final class Bench {
    public static void main(String[] a) throws Exception {
        Path corpus = Path.of(a.length > 0 ? a[0] : "../corpus");
        for (String[] c : new String[][] {{"30_customer_master", "fixed", "173", "cp037"}, {"31_insurance_claim", "rdw", "0", "cp037"},
                {"32_bank_transaction", "fixed", "0", "cp1140"}}) {
            Node root = CopybookParser.parse(corpus.resolve("copybooks/" + c[0] + ".cpy")).record(null);
            byte[] data = Files.readAllBytes(corpus.resolve("data/" + c[0] + ".bin"));
            List<byte[]> recs = new ArrayList<>();
            if (c[1].equals("rdw")) {
                for (int i = 0; i < data.length; ) {
                    int n = ((data[i] & 0xFF) << 8) | (data[i + 1] & 0xFF);
                    recs.add(Arrays.copyOfRange(data, i + 4, i + n));
                    i += n;
                }
            } else {
                for (int i = 0; i < data.length; i += root.size()) recs.add(Arrays.copyOfRange(data, i, i + root.size()));
            }
            RecordDecoder d = new RecordDecoder(root, new DecodeOptions().codepage(c[3]));
            ConnectSchemas s = new ConnectSchemas(d, "bench");
            long bytes = 0;
            for (int w = 0; w < 200_000; w++) s.toStruct(d.decode(recs.get(w % recs.size())));
            int n = 1_000_000;
            long t0 = System.nanoTime();
            for (int i = 0; i < n; i++) {
                byte[] r = recs.get(i % recs.size());
                bytes += r.length;
                s.toStruct(d.decode(r));
            }
            double sec = (System.nanoTime() - t0) / 1e9;
            System.out.printf("%-22s %,10.0f records/s  %6.1f MB/s  (avg %d bytes/record, 1 thread, bytes->Struct)%n",
                    c[0], n / sec, bytes / sec / 1e6, bytes / n);
        }
    }
}
