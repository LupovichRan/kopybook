       01  RENAME-REC.
           05  FIRST-NAME         PIC X(10).
           05  LAST-NAME          PIC X(15).
           05  PHONE-AREA         PIC 9(3).
           05  PHONE-NUM          PIC 9(7).
       66  FULL-NAME   RENAMES FIRST-NAME THRU LAST-NAME.
       66  PHONE       RENAMES PHONE-AREA THROUGH PHONE-NUM.
       66  SURNAME     RENAMES LAST-NAME.
