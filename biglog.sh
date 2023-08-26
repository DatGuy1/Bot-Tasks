rm wikiwork.out
rm wikiwork.log
rm imageresizer.out
rm afreporter.err
rm footy.err
rm playerstats.out
rm playerstats.err
find "/data/project/datbot/Tasks/NonFreeImageResizer/files" -iname "*.png" -type f -delete
find "/data/project/datbot/Tasks/NonFreeImageResizer/files" -iname "*.jpg" -type f -delete
find "/data/project/datbot/Tasks/NonFreeImageResizer/files" -iname "*.jpeg" -type f -delete
find "/data/project/datbot/Tasks/NonFreeImageResizer/files" -iname "*.webp" -type f -delete
find "/data/project/datbot/Tasks/NonFreeImageResizer/files" -iname "*.tif" -type f -delete
find "/data/project/datbot/Tasks/NonFreeImageResizer/files" -iname "*.svg" -type f -delete
find "/data/project/datbot/Tasks/NonFreeImageResizer/files" -iname "*.gif" -type f -delete
sleep 3
touch afreporter.err
touch imageresizer.out
touch wikiwork.out
touch wikiwork.log
touch footy.out
touch playerstats.out
touch playerstats.err
