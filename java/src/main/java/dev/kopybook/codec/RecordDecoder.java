package dev.kopybook.codec;

import dev.kopybook.copybook.Node;

import dev.kopybook.copybook.Condition88;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.*;

/**
 * Decodes one record into plain Java values: LinkedHashMap (groups), List (OCCURS),
 * String, Integer, Long, BigDecimal, Double, or null (unreadable REDEFINES view).
 * Walks the tree with a moving cursor, so OCCURS DEPENDING ON is handled naturally.
 * Thread-safe: all mutable state lives in a per-call context.
 */
public final class RecordDecoder {
    private final Node root;
    private final DecodeOptions o;
    private final Map<Node, LType> types = new IdentityHashMap<>();
    private final Map<String, Rule> rules = new HashMap<>();

    public RecordDecoder(Node root, DecodeOptions options) {
        this.root = root;
        this.o = options;
        for (Node n : root.walk()) if (!n.isGroup()) types.put(n, LType.of(n, o.trunc));
        if (o.redefinesWhen != null && !o.redefinesWhen.isEmpty()) {
            if (o.redefines != DecodeOptions.Redefines.ALL)
                throw new IllegalArgumentException("redefines.when needs the 'all' REDEFINES strategy");
            o.redefinesWhen.forEach((alt, cond) -> rules.put(alt, new Rule(root, alt, cond)));
        }
    }

    /** One view-selection rule: the view is decoded only when FIELD holds one of the values. */
    private static final class Rule {
        final String alt, field;
        final List<Object> values;

        Rule(Node root, String alt, String cond) {
            Map<String, Node> names = new HashMap<>();
            for (Node n : root.walk()) names.putIfAbsent(n.name, n);
            Node a = names.get(alt);
            if (a == null || (a.redefines() == null && !a.isRedefined()))
                throw new IllegalArgumentException("REDEFINES rule: " + alt + " is not part of a REDEFINES group");
            this.alt = alt;
            int colon = cond.indexOf(':');
            if (colon >= 0) {
                field = cond.substring(0, colon).strip().toUpperCase(Locale.ROOT);
                if (!names.containsKey(field))
                    throw new IllegalArgumentException("REDEFINES rule for " + alt + ": field " + field + " not found");
                values = new ArrayList<>(Arrays.asList((Object[]) cond.substring(colon + 1).split("\\|", -1)));
            } else {
                String f = null;
                List<Object> v = null;
                for (Node n : root.walk())
                    for (Condition88 c : n.conditions())
                        if (c.name().equalsIgnoreCase(cond)) { f = n.name; v = c.values(); }
                if (f == null) throw new IllegalArgumentException("REDEFINES rule for " + alt + ": no 88-level named " + cond);
                field = f;
                values = v;
            }
        }

        private static int cmp(Object v, Object lit) {
            if (v instanceof String s) return s.stripTrailing().compareTo(String.valueOf(lit).stripTrailing());
            return new BigDecimal(v.toString()).compareTo(new BigDecimal(String.valueOf(lit).strip()));
        }

        private static boolean eq(Object v, Object lit) {
            try { return cmp(v, lit) == 0; } catch (NumberFormatException e) { return false; }
        }

        boolean matches(Map<String, Object> vals, int pos) {
            if (!vals.containsKey(field))
                throw new DecodeException(alt, pos, "REDEFINES rule field " + field + " is not decoded before the view");
            Object v = vals.get(field);
            if (v == null) return false;
            for (Object lit : values) {
                if (lit instanceof List<?> l && l.size() == 3 && "THRU".equals(l.get(0))) {
                    try { if (cmp(v, l.get(1)) >= 0 && cmp(v, l.get(2)) <= 0) return true; }
                    catch (NumberFormatException ignored) { }
                } else if (eq(v, lit)) return true;
            }
            return false;
        }
    }

    public Node root() { return root; }
    public DecodeOptions options() { return o; }
    public LType type(Node n) { return types.get(n); }

    public static String fillerName(Node n) { return "filler_" + n.offset(); }

    private static final class Ctx {
        final Map<String, Long> odo = new HashMap<>();
        final Map<String, Object> vals = new HashMap<>();
        int pos;
    }

    public Map<String, Object> decode(byte[] data) {
        Ctx c = new Ctx();
        Map<String, Object> out;
        if (root.children().isEmpty()) {
            out = new LinkedHashMap<>();
            out.put(root.outName(), single(root, data, c));
        } else {
            out = group(root, data, c);
        }
        if (c.pos != data.length && !o.allowTrailing)
            throw new DecodeException(root.path(), c.pos, (data.length - c.pos) + " trailing bytes after record (record ends at " + c.pos + ")");
        return out;
    }

    private Map<String, Object> group(Node node, byte[] data, Ctx c) {
        Map<String, Object> out = new LinkedHashMap<>();
        List<Node> kids = node.children();
        int i = 0;
        while (i < kids.size()) {
            Node k = kids.get(i);
            int j = i + 1;
            while (j < kids.size() && kids.get(j).redefines() != null) j++;
            if (j == i + 1) {
                put(out, k, item(k, data, c));
            } else {
                int start = c.pos, end = start;
                Set<String> selected = null;
                if (!rules.isEmpty()) {
                    boolean ruled = false;
                    Set<String> hit = new HashSet<>(), rest = new HashSet<>();
                    for (int a = i; a < j; a++) {
                        String nm = kids.get(a).name;
                        Rule r = rules.get(nm);
                        if (r == null) rest.add(nm);
                        else { ruled = true; if (r.matches(c.vals, start)) hit.add(nm); }
                    }
                    if (ruled) selected = hit.isEmpty() ? rest : hit;
                }
                for (int a = i; a < j; a++) {
                    Node alt = kids.get(a);
                    end = Math.max(end, start + alt.size() * (alt.occursMax() == null ? 1 : alt.occursMax()));
                    if (o.redefines == DecodeOptions.Redefines.FIRST && a > i) continue;
                    c.pos = start;
                    Object v;
                    if (selected != null) {
                        v = selected.contains(alt.name) ? item(alt, data, c) : null;
                    } else if (o.redefines == DecodeOptions.Redefines.FIRST) {
                        v = item(alt, data, c);
                    } else {
                        try {
                            v = item(alt, data, c);
                        } catch (DecodeException | FieldException e) {
                            v = null;
                        }
                    }
                    put(out, alt, v);
                }
                if (end > data.length) throw new DecodeException(node.path(), end, "record too short");
                c.pos = end;
            }
            i = j;
        }
        return out;
    }

    private void put(Map<String, Object> out, Node n, Object v) {
        if (n.isFiller()) {
            if (o.keepFiller) out.put(fillerName(n), v);
            return;
        }
        out.put(n.outName(), v);
    }

    private Object item(Node n, byte[] data, Ctx c) {
        if (!n.isArray()) return single(n, data, c);
        long count;
        if (n.dependingOn() != null) {
            Long v = c.odo.get(n.dependingOn());
            if (v == null) throw new DecodeException(n.path(), c.pos, "DEPENDING ON " + n.dependingOn() + " not decoded before table");
            count = v;
            if (count < n.occursMin() || count > n.occursMax()) {
                if (o.odoStrict)
                    throw new DecodeException(n.path(), c.pos, n.dependingOn() + " value outside " + n.occursMin() + ".." + n.occursMax());
                count = Math.max(n.occursMin(), Math.min(count, n.occursMax()));
            }
        } else {
            count = n.occursMax();
        }
        List<Object> vals = new ArrayList<>((int) count);
        for (int i = 0; i < count; i++) vals.add(single(n, data, c));
        return vals;
    }

    private Object single(Node n, byte[] data, Ctx c) {
        if (!n.children().isEmpty()) return group(n, data, c);
        int pos = c.pos, end = pos + n.size();
        if (end > data.length)
            throw new DecodeException(n.path(), pos, "record too short (need " + end + " bytes, have " + data.length + ")");
        Object v;
        try {
            v = leaf(n, data, pos, c);
        } catch (FieldException e) {
            throw new DecodeException(n.path(), pos, e.getMessage());
        }
        c.pos = end;
        c.vals.put(n.name, v);
        return v;
    }

    private Object leaf(Node n, byte[] b, int pos, Ctx c) {
        switch (n.kind()) {
            case ALNUM, EDITED:
                return FieldCodec.text(b, pos, n.size(), o.charset, o.trim);
            case FLOAT:
                return FieldCodec.hfp(b, pos, n.size());
            default:
                break;
        }
        var p = n.pic();
        BigInteger u;
        switch (n.usage()) {
            case DISPLAY -> u = FieldCodec.zoned(b, pos, n.size(), p.signed, n.signLeading(), n.signSeparate());
            case PACKED -> u = FieldCodec.packed(b, pos, n.size(), p.digits, p.signed);
            case BINARY, NATIVE -> {
                u = FieldCodec.binary(b, pos, n.size(), p.signed);
                if (n.usage() == Node.Usage.BINARY && "std".equals(o.trunc) && u.abs().compareTo(BigInteger.TEN.pow(p.digits)) >= 0)
                    throw new FieldException("binary value exceeds PIC digits (" + p.digits + ") in " + n.size() + "-byte field; use COMP-5 or trunc=bin");
            }
            default -> throw new FieldException("unsupported usage " + n.usage());
        }
        return value(n, u, c);
    }

    private Object value(Node n, BigInteger u, Ctx c) {
        LType t = types.get(n);
        if (n.pic().scale == 0 && u.bitLength() < 63) c.odo.put(n.name, u.longValue());
        try {
            return switch (t.kind()) {
                case INT -> u.intValueExact();
                case LONG -> u.longValueExact();
                default -> FieldCodec.scaled(u, n.pic().scale);
            };
        } catch (ArithmeticException e) {
            // R2 guard: an over-wide value (e.g. COMP-3 overflow) must surface as FieldException, which
            // single() wraps in DecodeException. Not reachable through decode() today, because packed()
            // and LType already bound values by PIC digits/storage size; kept as defence in depth.
            throw new FieldException("value does not fit " + t.kind());
        }
    }
}
