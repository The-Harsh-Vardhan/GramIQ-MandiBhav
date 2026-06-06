export function CallToActionBox() {
  return (
    <div className="rounded-3xl border border-[#38bdf8]/20 bg-gradient-to-br from-[#38bdf8]/5 to-[#0284c7]/5 p-6 shadow-[0_12px_40px_rgba(2,132,199,0.03)] hover:shadow-[0_12px_45px_rgba(2,132,199,0.06)] transition-all duration-300">
      <div className="flex items-center gap-3">
        <span className="flex items-center justify-center w-9 h-9 rounded-2xl bg-[#25D366] text-white shadow-md shadow-[#25D366]/20">
          <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M.057 24l1.687-6.163c-1.041-1.804-1.588-3.849-1.587-5.946C.06 5.348 5.397.01 12.008.01c3.202.001 6.212 1.246 8.477 3.513 2.262 2.268 3.507 5.28 3.505 8.484-.004 6.657-5.34 11.997-11.953 11.997-2.005-.001-3.973-.502-5.724-1.455L0 24zm6.59-4.846c1.6.95 3.488 1.459 5.407 1.46 5.412 0 9.817-4.402 9.82-9.817.002-2.624-1.02-5.09-2.885-6.958C17.12 1.972 14.654 1.95 12.01 1.95c-5.41 0-9.818 4.403-9.822 9.82-.001 1.902.497 3.76 1.44 5.346L2.6 21.684l4.047-1.06c.01-.005.022-.01.03-.015z" />
          </svg>
        </span>
        <div>
          <h3 className="font-serif text-lg font-bold text-soil leading-tight">Mandi Rates on WhatsApp</h3>
          <p className="text-[10px] text-river uppercase font-bold tracking-wider mt-0.5">Instant Daily Alerts</p>
        </div>
      </div>
      <p className="mt-4 text-sm text-slate-600 leading-relaxed">
        Pehle bhav jano, phir becho! Join our WhatsApp updates to receive average modal pricing benchmarks for Soybean and Cotton markets directly in your chat.
      </p>
      <a 
        href="https://wa.me/919999999999?text=Subscribe%20MandiBhav" 
        target="_blank"
        rel="noopener noreferrer"
        className="mt-6 block w-full text-center rounded-2xl bg-soil text-white py-3.5 text-sm font-semibold hover:bg-field shadow-lg shadow-soil/15 hover:shadow-field/20 hover:scale-[1.01] active:scale-[0.99] transition-all duration-200"
      >
        Subscribe via WhatsApp
      </a>
    </div>
  );
}
