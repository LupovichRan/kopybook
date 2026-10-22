package dev.kopybook.connect;

import dev.kopybook.codec.DecodeException;
import dev.kopybook.codec.FieldException;
import dev.kopybook.copybook.CopybookException;
import org.apache.kafka.common.config.ConfigDef;
import org.apache.kafka.connect.data.Schema;
import org.apache.kafka.connect.data.SchemaAndValue;
import org.apache.kafka.connect.data.Struct;
import org.apache.kafka.connect.errors.DataException;
import org.apache.kafka.connect.storage.Converter;
import org.apache.kafka.connect.storage.ConverterConfig;
import org.apache.kafka.connect.storage.ConverterType;

import java.util.HashMap;
import java.util.Map;

/**
 * Kafka Connect Converter: EBCDIC record bytes <-> Struct, driven by a copybook.
 * Use as key.converter / value.converter with prefix, e.g.
 * value.converter=dev.kopybook.connect.CopybookConverter, value.converter.copybook.path=/etc/kopybook/cust.cpy
 */
public class CopybookConverter implements Converter {
    private CopybookConfig cfg;

    @Override
    public void configure(Map<String, ?> configs, boolean isKey) {
        Map<String, Object> props = new HashMap<>(configs);
        props.remove(ConverterConfig.TYPE_CONFIG);
        try {
            cfg = new CopybookConfig(props);
        } catch (CopybookException e) {
            throw new org.apache.kafka.common.config.ConfigException("invalid copybook: " + e.getMessage());
        }
    }

    public ConfigDef config() {
        return CopybookConfig.DEF;
    }

    public Schema schema() {
        return cfg.schemas.schema();
    }

    @Override
    public SchemaAndValue toConnectData(String topic, byte[] value) {
        if (value == null) return new SchemaAndValue(cfg.schemas.schema().schema(), null);
        try {
            Map<String, Object> m = cfg.decoder.decode(cfg.unframe(value));
            return new SchemaAndValue(cfg.schemas.schema(), cfg.schemas.toStruct(m));
        } catch (DecodeException | FieldException e) {
            throw new DataException("kopybook: cannot decode record from topic " + topic + ": " + e.getMessage(), e);
        }
    }

    @Override
    public byte[] fromConnectData(String topic, Schema schema, Object value) {
        if (value == null) return null;
        if (!(value instanceof Struct s)) throw new DataException("kopybook: expected Struct, got " + value.getClass());
        try {
            return cfg.frame(cfg.encoder.encode(ConnectSchemas.toMap(s)));
        } catch (FieldException e) {
            throw new DataException("kopybook: cannot encode record for topic " + topic + ": " + e.getMessage(), e);
        }
    }
}
