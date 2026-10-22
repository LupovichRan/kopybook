package dev.kopybook;

import dev.kopybook.copybook.CopybookException;
import dev.kopybook.copybook.CopybookParser;
import dev.kopybook.copybook.Node;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class ParserTest {
    static Node rec(String f) throws Exception {
        return CopybookParser.parse(Corpus.DIR.resolve("copybooks").resolve(f + ".cpy")).record(null);
    }

    @ParameterizedTest
    @CsvSource({"01_alnum_basic,51", "02_zoned_unsigned,54", "03_zoned_signed_trailing,37", "06_comp_binary,34",
            "08_comp5_native,32", "09_comp3_packed,26", "10_comp3_large,83", "11_occurs_fixed,89", "12_occurs_group,72",
            "13_occurs_nested,118", "17_redefines_simple,12", "19_redefines_multi,25", "22_filler,23", "27_float_hfp,32",
            "28_numeric_edited,46", "29_fixed_format_columns,78", "30_customer_master,173", "36_free_format_lowercase,20"})
    void lengths(String f, int len) throws Exception {
        assertEquals(len, rec(f).size());
    }

    @Test
    void continuationLiteral() throws Exception {
        Node r = rec("29_fixed_format_columns");
        assertEquals("A LONG LITERAL THAT CONTINUES", r.children().get(3).value());
    }

    @Test
    void renamesAndConditions() throws Exception {
        Node r = rec("21_level66_renames");
        assertEquals(3, r.renames().size());
        Node s = rec("20_level88_conditions").children().get(0);
        assertEquals(3, s.conditions().size());
    }

    @ParameterizedTest
    @CsvSource(value = {"05  A PIC S9(4) COMP SYNC.|SYNCHRONIZED", "05  A PIC 9(3)PP.|scaling", "05  A PIC N(10).|national",
            "05  A PIC X(4) USAGE NATIONAL.|NATIONAL", "05  A PIC S9(19) COMP.|binary"}, delimiter = '|')
    void unsupported(String body, String msg) {
        Exception e = assertThrows(CopybookException.Unsupported.class,
                () -> CopybookParser.parse("       01  R.\n           " + body + "\n"));
        assertTrue(e.getMessage().toLowerCase().contains(msg.toLowerCase()), e.getMessage());
    }

    @Test
    void errorsCarryLineNumbers() {
        CopybookException e = assertThrows(CopybookException.class,
                () -> CopybookParser.parse("       01  R.\n           05  A PIC X.\n           05  B PIC X(3) FOO.\n"));
        assertEquals(3, e.line());
    }
}
