       01  STATUS-REC.
           05  ACCT-STATUS        PIC X.
               88  ST-ACTIVE      VALUE 'A'.
               88  ST-CLOSED      VALUES ARE 'C' 'X'.
               88  ST-ANY-OPEN    VALUE 'A' THRU 'B'.
           05  RISK-SCORE         PIC 9(3).
               88  LOW-RISK       VALUE 0 THRU 299.
               88  MED-RISK       VALUE 300 THROUGH 699.
               88  HIGH-RISK      VALUE 700 THRU 999.
           05  VIP-FLAG           PIC X VALUE 'N'.
               88  IS-VIP         VALUE 'Y'.
               88  NOT-VIP        VALUE 'N' SPACE.
