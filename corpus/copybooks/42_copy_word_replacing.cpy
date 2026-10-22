      * word-level REPLACING and a member found on the copy path
       01  LEDGER-REC.
           05  LG-KEY             PIC X(10).
           COPY AMTFLDS REPLACING AMT-GROSS BY LG-DEBIT
                                  AMT-NET   BY LG-CREDIT
                                  ==10== BY ==05==.
