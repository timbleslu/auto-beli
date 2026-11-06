import hashlib
from PIL import Image
import pytest
from beli_tool.exports import make_copy


def test_full_size_copy_strips_metadata_and_preserves_original(tmp_path):
    original=tmp_path/'original.jpg';output=tmp_path/'private/copy.jpg'
    image=Image.new('RGB',(1600,1200),'red')
    exif=Image.Exif();exif[270]='private caption';exif[315]='private name';exif[34853]={1:'N',2:(40.0,0.0,0.0)}
    image.save(original,exif=exif)
    before=hashlib.sha256(original.read_bytes()).hexdigest()
    digest=make_copy(original,output)
    assert digest==hashlib.sha256(output.read_bytes()).hexdigest()
    assert hashlib.sha256(original.read_bytes()).hexdigest()==before
    with Image.open(output) as photo:
        assert photo.size==(1600,1200)
        assert not photo.getexif()
        assert not any(k in photo.info for k in ('exif','xmp','iptc'))
    assert output.stat().st_mode & 0o077==0


def test_thumbnail_is_not_used_for_attachment(tmp_path):
    original=tmp_path/'small.jpg';Image.new('RGB',(100,100)).save(original)
    with pytest.raises(ValueError): make_copy(original,tmp_path/'copy.jpg')
    assert not (tmp_path/'copy.jpg').exists()
