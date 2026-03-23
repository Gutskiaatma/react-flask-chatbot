cd frontend
npm install
npm run build

# remove old static (important)
rm -rf ../backend/static

# copy new build
cp -r dist ../backend/static