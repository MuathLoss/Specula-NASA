import csv
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from export_all import split_csv,preflight,run


def test_chunking_preserves_all_rows_headers_and_unicode():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);rows=[['id','value']]+[[str(i),'é, value '+str(i)] for i in range(20)]
        with (root/'in.csv').open('w',newline='',encoding='utf-8') as f:csv.writer(f).writerows(rows)
        chunks=split_csv(root/'in.csv',root/'parts',max_bytes=100)
        recovered=[]
        for c in chunks:
            assert c['bytes']<=100
            with (root/'parts'/c['file']).open(newline='',encoding='utf-8') as f:
                r=list(csv.reader(f));assert r[0]==rows[0];recovered.extend(r[1:])
        assert recovered==rows[1:] and sum(c['rows'] for c in chunks)==20


def test_empty_catalog_still_exports_header():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);(root/'in.csv').write_text('a,b\n')
        chunks=split_csv(root/'in.csv',root/'parts',100)
        assert len(chunks)==1 and chunks[0]['rows']==0
        assert (root/'parts'/chunks[0]['file']).read_text()=='a,b\n'


def test_missing_tables_stop_before_creating_output():
    with TemporaryDirectory() as tmp:
        root=Path(tmp)
        assert run(root,root/'out',root/'bundle',patches=['ceres'])==2
        assert not (root/'out').exists() and not (root/'bundle').exists()


def test_existing_output_is_never_overwritten():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);(root/'out').mkdir()
        try:run(root,root/'out',root/'bundle',patches=['ceres'])
        except FileExistsError:pass
        else:raise AssertionError('Existing output was not protected')
