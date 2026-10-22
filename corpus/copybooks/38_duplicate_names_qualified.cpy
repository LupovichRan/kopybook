      * same field names under different groups
       01  SHIPMENT-REC.
           05  BILL-TO.
               10  NAME           PIC X(20).
               10  ADDR.
                   15  STREET     PIC X(25).
                   15  ZIP        PIC 9(5).
           05  SHIP-TO.
               10  NAME           PIC X(20).
               10  ADDR.
                   15  STREET     PIC X(25).
                   15  ZIP        PIC 9(5).
           05  WEIGHT             PIC 9(5)V9 COMP-3.
