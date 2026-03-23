cd ../frontend
npm install
npm run build

rm -rf ../backend/static
cp -r dist ../backend/static
