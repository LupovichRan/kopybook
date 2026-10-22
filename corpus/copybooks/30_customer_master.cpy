      * synthetic retail-bank customer master
       01  CUSTOMER-MASTER.
           05  CM-KEY.
               10  CM-BRANCH      PIC 9(4).
               10  CM-CUST-NO     PIC 9(10).
           05  CM-NAME.
               10  CM-LAST        PIC X(25).
               10  CM-FIRST       PIC X(15).
               10  CM-MIDDLE      PIC X.
           05  CM-DOB             PIC 9(8).
           05  CM-SEGMENT         PIC X(2).
               88  CM-RETAIL      VALUE 'RT'.
               88  CM-PRIVATE     VALUE 'PB'.
           05  CM-ADDRESS.
               10  CM-STREET      PIC X(30).
               10  CM-CITY        PIC X(20).
               10  CM-ZIP         PIC 9(7).
           05  CM-BALANCES.
               10  CM-CURRENT     PIC S9(11)V99 COMP-3.
               10  CM-AVAILABLE   PIC S9(11)V99 COMP-3.
               10  CM-OVERDRAFT   PIC S9(7)V99  COMP-3.
           05  CM-OPENED          PIC 9(8).
           05  CM-BRANCH-HIST     PIC 9(4) OCCURS 3 TIMES.
           05  CM-CREDIT-SCORE    PIC S9(4) COMP.
           05  FILLER             PIC X(10).
