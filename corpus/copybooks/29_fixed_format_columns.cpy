000100******************************************************************SEQ00001
000200* FIXED-FORMAT SOURCE: SEQUENCE AREA, COMMENTS AND COLS 73-80     SEQ00002
000300******************************************************************SEQ00003
000400 01  FIXED-REC.                                                   SEQ00004
000500     05  F-ID               PIC 9(6).                             SEQ00005
000600     05  F-NAME             PIC X(25).                            SEQ00006
000700/    PAGE EJECT LINE                                              SEQ00007
000800     05  F-AMOUNT           PIC S9(7)V99                          SEQ00008
000900                            COMP-3.                               SEQ00009
001000     05  F-DESC             PIC X(40) VALUE 'A LONG LITERAL THAT CSEQ00010
001100-                          'ONTINUES'.                            SEQ00011
001200     05  F-CODE             PIC XX.                               SEQ00012
