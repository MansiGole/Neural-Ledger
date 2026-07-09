const express = require('express');
const routes = require('./routes');

const app = express();
const port = 3000;

app.use(express.json());
app.use(require('cors')());

app.get('/', (req, res) => {
  res.json({ message: 'Webhook reconciliation mock API is running' });
});

app.use('/', routes);

app.listen(port, () => {
  console.log(`Server running on port ${port}`);
});
