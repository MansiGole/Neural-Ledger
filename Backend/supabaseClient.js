// supabaseClient.js
// Initializes and exports a single reusable Supabase client instance.
// All services import from here so credentials are configured in one place.

// Backend/supabaseClient.js

const { createClient } = require("@supabase/supabase-js");
require("dotenv").config();

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY
);

module.exports = supabase;