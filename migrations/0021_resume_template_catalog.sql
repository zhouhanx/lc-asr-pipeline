ALTER TABLE resume_documents
    DROP CONSTRAINT resume_documents_template_key_check;

ALTER TABLE resume_documents
    ADD CONSTRAINT resume_documents_template_key_check
    CHECK (template_key IN (
        'classic', 'sidebar', 'timeline',
        'qmj-1045', 'qmj-1015', 'qmj-1004', 'qmj-1044', 'qmj-1012',
        'qmj-1005', 'qmj-1046', 'qmj-1019', 'qmj-1011', 'qmj-1008',
        'qmj-1041', 'qmj-1023', 'qmj-1035', 'qmj-1034', 'qmj-1016',
        'qmj-1020', 'qmj-1040', 'qmj-1033', 'qmj-1022', 'qmj-1002',
        'qmj-1043', 'qmj-1039', 'qmj-1038', 'qmj-1042', 'qmj-1014',
        'qmj-1030', 'qmj-1027', 'qmj-1032', 'qmj-1003', 'qmj-1037',
        'qmj-1025', 'qmj-1036', 'qmj-1021', 'qmj-1006', 'qmj-1007',
        'qmj-1029', 'qmj-1031', 'qmj-1013', 'qmj-1024', 'qmj-1028',
        'qmj-1001', 'qmj-1018', 'qmj-1026', 'qmj-1009', 'qmj-1000',
        'qmj-1010', 'qmj-1017',
        'local-data-ribbon', 'local-data-compact'
    ));
