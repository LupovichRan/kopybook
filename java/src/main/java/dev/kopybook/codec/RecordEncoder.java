package dev.kopybook.codec;

import dev.kopybook.copybook.Node;

import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.*;

/** Encodes plain Java values (as produced by RecordDecoder) back into EBCDIC bytes. */
public final class RecordEncoder {
    private final Node root;
    private final DecodeOptions o;

    public RecordEncoder(Node root, DecodeOptions options) {
        this.root = root;
        this.o = options;
    }

    public byte[] encode(Map<String, ?> value) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        group(root, value, out, new HashMap<>());
        return out.toByteArray();
    }

    private void group(Node node, Map<String, ?> value, ByteArrayOutputStream out, Map<String, Long> ctx) {
        Map<String, ?> v = value == null ? Map.of() : value;
        List<Node> kids = node.children();
        int i = 0;
        while (i < kids.size()) {
            Node c = kids.get(i);
            int j = i + 1;
            while (j < kids.size() && kids.get(j).redefines() != null) j++;
            if (j == i + 1) {
                item(c, c.isFiller() ? null : v.get(c.outName()), out, ctx);
            } else {
                int width = 0;
                Node active = c;
                for (int a = i; a < j; a++) {
                    Node alt = kids.get(a);
                    width = Math.max(width, alt.size() * (alt.occursMax() == null ? 1 : alt.occursMax()));
                }
                for (int a = i; a < j; a++)
                    if (v.get(kids.get(a).outName()) != null) { active = kids.get(a); break; }
                ByteArrayOutputStream tmp = new ByteArrayOutputStream();
                item(active, v.get(active.outName()), tmp, ctx);
                byte[] b = tmp.toByteArray();
                out.writeBytes(b);
                out.writeBytes(FieldCodec.encodeText("", width - b.length, o.charset));
            }
            i = j;
        }
    }

    @SuppressWarnings("unchecked")
    private void item(Node n, Object value, ByteArrayOutputStream out, Map<String, Long> ctx) {
        if (!n.isArray()) {
            single(n, value, out, ctx);
            return;
        }
        List<Object> vals = value == null ? null : (List<Object>) value;
        long count;
        if (n.dependingOn() != null) {
            Long cnt = ctx.get(n.dependingOn());
            if (cnt == null) throw new FieldException(n.path() + ": ODO object " + n.dependingOn() + " not encoded first");
            count = cnt;
            if (vals == null) vals = List.of();
            if (vals.size() != count) throw new FieldException(n.path() + ": " + vals.size() + " items do not match " + n.dependingOn());
        } else {
            count = n.occursMax();
            if (vals == null) vals = Collections.nCopies((int) count, null);
            if (vals.size() != count) throw new FieldException(n.path() + ": expected " + count + " items, got " + vals.size());
        }
        for (Object x : vals) single(n, x, out, ctx);
    }

    @SuppressWarnings("unchecked")
    private void single(Node n, Object value, ByteArrayOutputStream out, Map<String, Long> ctx) {
        if (!n.children().isEmpty()) {
            group(n, (Map<String, ?>) value, out, ctx);
            return;
        }
        switch (n.kind()) {
            case ALNUM, EDITED -> {
                out.writeBytes(FieldCodec.encodeText(value == null ? "" : value.toString(), n.size(), o.charset));
                return;
            }
            case FLOAT -> throw new FieldException(n.path() + ": encoding COMP-1/COMP-2 is not implemented");
            default -> { }
        }
        var p = n.pic();
        BigDecimal d;
        try {
            d = value == null ? BigDecimal.ZERO : new BigDecimal(value.toString());
        } catch (NumberFormatException e) {
            throw new FieldException(n.path() + ": value is not a number");
        }
        BigInteger u;
        try {
            u = d.setScale(p.scale).unscaledValue();
        } catch (ArithmeticException e) {
            throw new FieldException(n.path() + ": value has more than " + p.scale + " decimals");
        }
        if (p.scale == 0) ctx.put(n.name, u.longValue());
        switch (n.usage()) {
            case DISPLAY -> out.writeBytes(FieldCodec.encodeZoned(u, p.digits, p.signed, n.signLeading(), n.signSeparate()));
            case PACKED -> {
                if (u.abs().toString().length() > p.digits) throw new FieldException(n.path() + ": value does not fit " + p.digits + " digits");
                out.writeBytes(FieldCodec.encodePacked(u, p.signed, n.size()));
            }
            case BINARY, NATIVE -> {
                if (n.usage() == Node.Usage.BINARY && "std".equals(o.trunc) && u.abs().compareTo(BigInteger.TEN.pow(p.digits)) >= 0)
                    throw new FieldException(n.path() + ": value does not fit " + p.digits + " digits");
                out.writeBytes(FieldCodec.encodeBinary(u, p.signed, n.size()));
            }
            default -> throw new FieldException("unsupported usage " + n.usage());
        }
    }
}
