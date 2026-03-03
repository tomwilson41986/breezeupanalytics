/**
 * Netlify serverless function — OBS API Proxy
 *
 * Proxies requests to the OBS WordPress REST API to avoid CORS issues.
 * The OBS catalog SPA API returns JSON with all hip data for a sale.
 *
 * Usage: /.netlify/functions/obs-proxy?saleId=142
 */

const OBS_API_BASE =
  "https://obssales.com/wp-json/obs-catalog-wp-plugin/v1";

export default async (req) => {
  const url = new URL(req.url);
  const saleId = url.searchParams.get("saleId");

  // CORS headers
  const corsHeaders = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };

  // Handle preflight
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  if (!saleId) {
    return new Response(
      JSON.stringify({ error: "saleId query parameter is required" }),
      {
        status: 400,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      }
    );
  }

  try {
    const apiUrl = `${OBS_API_BASE}/horse-sales/${encodeURIComponent(saleId)}`;

    const response = await fetch(apiUrl, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      return new Response(
        JSON.stringify({
          error: `OBS API returned ${response.status}`,
        }),
        {
          status: response.status,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        }
      );
    }

    const data = await response.json();

    return new Response(JSON.stringify(data), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "public, max-age=300, s-maxage=600",
        ...corsHeaders,
      },
    });
  } catch (err) {
    return new Response(
      JSON.stringify({ error: "Failed to fetch from OBS API", detail: err.message }),
      {
        status: 502,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      }
    );
  }
};
