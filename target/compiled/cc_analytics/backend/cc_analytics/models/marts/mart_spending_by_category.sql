with transactions as (
    select * from "postgres"."public_public"."int_transactions_cleaned"
    where transaction_type = 'debit'
),
monthly_category as (
    select 
        transaction_month,
        category_name,
        count(*) as transaction_count,
        sum(amount) as total_spend,
        avg(amount) as avg_spending,
        min(amount) as min_transaction,
        max(amount) as max_transaction,
        round(sum(amount)/sum(sum(amount)) over(
            partition by transaction_month)*100,2) as pct_monthly_spend
        from    
            transactions
        group by
             transaction_month,
             category_name       
        ),
final as (
    select 
        transaction_month,
        category_name,
        transaction_count,
        round(total_spend,2) as total_spend,
        round(avg_spending,2) as avg_spending,
        round(min_transaction,2) as min_transaction,
        round(max_transaction,2) as max_transaction,
        pct_monthly_spend
        from 
            monthly_category
)    
select * from final
order by 
    transaction_month desc,
    total_spend desc