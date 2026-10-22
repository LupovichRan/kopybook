      * COPY with REPLACING: partial-word :TAG:, pseudo-text, LEADING,
      * library qualifier and a nested COPY
       01  PARTY-REC.
           05  PARTY-ID           PIC 9(8).
           COPY ADDRFLDS OF COPYLIB REPLACING ==:PFX:== BY ==BILL==.
           COPY ADDRFLDS OF COPYLIB REPLACING ==:PFX:== BY ==SHIP==.
           05  PARTY-AMOUNTS.
               COPY AMTFLDS IN COPYLIB
                   REPLACING ==S9(7)V99== BY ==S9(9)V99==
                             LEADING ==AMT-== BY ==PTY-==.
           COPY TRAILER.
